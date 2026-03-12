"""ChatService — orchestrates the general health chat feature."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.core import AgentCore
from app.agents.definitions import CHAT_AGENT
from app.agents.session import AgentSession
from app.agents.types import AgentEvent, AgentEventType
from app.core.exceptions import AppError
from app.models.chat import ChatConversation, ChatMessage
from app.models.profile import Profile
from app.schemas.action_log import ActionType
from app.schemas.chat import ChatConversationResponse, ChatMessageResponse, ChatTurnResponse
from app.schemas.common import PaginatedResponse
from app.services.action_log import ActionLogService
from app.services.chat_prompts import CHAT_DISCLAIMER, CHAT_SYSTEM_PROMPT, TOPIC_EXTRACTION_PROMPT
from app.services.chat_safety import (
    detect_mental_health_crisis,
    get_crisis_response,
    sanitize_response,
    validate_response,
)
from app.services.context_builder import ContextBuilder
from app.services.llm import ImagePart, LLMMessage, LLMRequest, LLMTask
from app.services.memory import build_conversation_window
from app.services.memory_extractor import MemoryExtractor
from app.services.message_parts_builder import (
    PartsAccumulator,
    build_assistant_parts,
    build_assistant_parts_from_result,
    build_user_parts,
    upload_images_for_parts,
)

logger = logging.getLogger(__name__)

MAX_HISTORY_TOKENS = 3000


class ChatService:
    """Orchestrates the general health chat feature.

    Responsibilities:
    - Conversation CRUD
    - Context assembly and LLM orchestration
    - Response safety validation
    - Memory integration
    - Action logging
    """

    def __init__(
        self,
        db: AsyncSession,
        agent_core: AgentCore,
        context_builder: ContextBuilder,
        memory_extractor: MemoryExtractor,
    ) -> None:
        self._db = db
        self._agent = agent_core
        self._ctx = context_builder
        self._mem_extractor = memory_extractor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_message(
        self,
        profile: Profile,
        content: str,
        conversation_id: UUID | None = None,
        topic: str | None = None,
        image_parts: list[ImagePart] | None = None,
    ) -> tuple[ChatConversation, ChatTurnResponse]:
        """Send a chat message and get the AI response.

        If conversation_id is provided, continues that conversation.
        Otherwise creates a new one.

        Returns (conversation, turn_response).
        """
        # 1. Resolve or create conversation
        is_new_conversation = False
        if conversation_id:
            conversation = await self.get_conversation(conversation_id, profile.id)
            if not conversation:
                raise AppError(
                    status_code=404,
                    detail="Conversation not found",
                    code="NOT_FOUND",
                )
        else:
            conversation = ChatConversation(profile_id=profile.id, topic=topic)
            self._db.add(conversation)
            await self._db.flush()
            is_new_conversation = True

        # 2. Mental health crisis pre-check
        if detect_mental_health_crisis(content):
            crisis_text = get_crisis_response()
            user_msg = ChatMessage(
                conversation_id=conversation.id,
                role="user",
                content=content,
                content_parts=build_user_parts(content),
            )
            assistant_msg = ChatMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=crisis_text,
                content_parts=build_assistant_parts_from_result(crisis_text),
            )
            now = datetime.now(timezone.utc)
            user_msg.created_at = now
            assistant_msg.created_at = now + timedelta(milliseconds=1)
            self._db.add_all([user_msg, assistant_msg])
            conversation.updated_at = func.now()
            await self._db.flush()
            await self._db.refresh(assistant_msg)

            await self._log_action(
                profile,
                ActionType.CHAT_MESSAGE,
                {
                    "conversation_id": str(conversation.id),
                    "topic": conversation.topic,
                    "message_preview": content[:100],
                    "crisis_detected": True,
                },
            )

            return conversation, ChatTurnResponse(
                message=ChatMessageResponse.model_validate(assistant_msg),
                disclaimer=CHAT_DISCLAIMER,
            )

        # 3. Build context
        ctx = await self._ctx.build(
            db=self._db,
            profile_id=profile.id,
            query=content,
            interaction_type="chat",
            memory_budget=1500,
            template=CHAT_SYSTEM_PROMPT,
        )

        # 4. Build conversation messages with sliding window
        messages = await self._build_conversation_messages(
            conversation.id, content, image_parts=image_parts
        )

        # 5. Generate response via AgentCore
        agent_session = AgentSession(
            profile_id=profile.id,
            system_prompt=ctx.system_prompt,
            messages=messages,
        )
        agent_result = await self._agent.run(agent_session, CHAT_AGENT)
        response_text = agent_result.content.strip()

        # 6. Safety validation
        violations = validate_response(response_text)
        response_text = sanitize_response(response_text, violations)

        # 7. Build rich content parts
        image_urls = (
            await upload_images_for_parts(image_parts, profile.id) if image_parts else None
        )
        user_parts = build_user_parts(content, image_urls)
        assistant_parts = build_assistant_parts_from_result(
            response_text,
            tool_calls=agent_result.tool_calls_made or None,
            tool_results=agent_result.tool_results or None,
            ctx=ctx,
        )

        # 8. Store messages and commit — commit early so the client can
        # immediately GET the conversation after receiving this response.
        # (get_db auto-commit runs after the response is sent, which creates
        # a race condition with the client navigating to the new resource.)
        user_msg = ChatMessage(
            conversation_id=conversation.id,
            role="user",
            content=content,
            content_parts=user_parts,
        )
        assistant_msg = ChatMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=response_text,
            content_parts=assistant_parts,
        )
        now = datetime.now(timezone.utc)
        user_msg.created_at = now
        assistant_msg.created_at = now + timedelta(milliseconds=1)
        self._db.add_all([user_msg, assistant_msg])
        conversation.updated_at = func.now()
        await self._db.commit()
        await self._db.refresh(assistant_msg)

        # 9. Auto-generate topic for new conversations (best-effort, after commit)
        if is_new_conversation and not topic:
            await self._auto_generate_topic(conversation, content)

        # 10. Log action
        await self._log_action(
            profile,
            ActionType.CHAT_MESSAGE,
            {
                "conversation_id": str(conversation.id),
                "topic": conversation.topic,
                "message_preview": content[:100],
            },
        )

        return conversation, ChatTurnResponse(
            message=ChatMessageResponse.model_validate(assistant_msg),
            disclaimer=CHAT_DISCLAIMER,
        )

    async def send_message_stream(
        self,
        profile: Profile,
        content: str,
        conversation_id: UUID | None = None,
        topic: str | None = None,
        image_parts: list[ImagePart] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Streaming version of send_message(). Yields events as they occur."""
        # 1. Resolve or create conversation
        is_new_conversation = False
        if conversation_id:
            conversation = await self.get_conversation(conversation_id, profile.id)
            if not conversation:
                raise AppError(status_code=404, detail="Conversation not found", code="NOT_FOUND")
        else:
            conversation = ChatConversation(profile_id=profile.id, topic=topic)
            self._db.add(conversation)
            # Commit early so the conversation is visible to other sessions
            # (e.g., if the client disconnects and refetches via GET later)
            await self._db.commit()
            is_new_conversation = True

        # Emit conversation_id immediately so the client can update its URL
        # and enable the GET query before any LLM work starts
        yield AgentEvent(
            type=AgentEventType.STATUS,
            data={
                "step": "session_created",
                "message": "Starting conversation...",
                "conversation_id": str(conversation.id),
            },
        )

        # 2. Mental health crisis pre-check
        if detect_mental_health_crisis(content):
            crisis_text = get_crisis_response()
            user_msg = ChatMessage(
                conversation_id=conversation.id,
                role="user",
                content=content,
                content_parts=build_user_parts(content),
            )
            assistant_msg = ChatMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=crisis_text,
                content_parts=build_assistant_parts_from_result(crisis_text),
            )
            now = datetime.now(timezone.utc)
            user_msg.created_at = now
            assistant_msg.created_at = now + timedelta(milliseconds=1)
            self._db.add_all([user_msg, assistant_msg])
            conversation.updated_at = func.now()
            await self._db.commit()
            await self._db.refresh(assistant_msg)

            yield AgentEvent(
                type=AgentEventType.TEXT_DELTA,
                data={"content": crisis_text},
            )
            yield AgentEvent(
                type=AgentEventType.DONE,
                data={
                    "content": crisis_text,
                    "id": str(assistant_msg.id),
                    "conversation_id": str(conversation.id),
                    "disclaimer": CHAT_DISCLAIMER,
                },
            )
            return

        # 3. Build context
        accumulator = PartsAccumulator()

        ctx_event = AgentEvent(
            type=AgentEventType.STATUS,
            data={"step": "context", "message": "Loading patient context..."},
        )
        accumulator.record_event(ctx_event)
        yield ctx_event

        ctx = await self._ctx.build(
            db=self._db,
            profile_id=profile.id,
            query=content,
            interaction_type="chat",
            memory_budget=1500,
            template=CHAT_SYSTEM_PROMPT,
        )

        # Emit detailed context results
        profile_name = ctx.profile_context.get("name", "patient")
        profile_event = AgentEvent(
            type=AgentEventType.STATUS,
            data={"step": "profile", "message": f"Loaded profile for {profile_name}"},
        )
        accumulator.record_event(profile_event)
        yield profile_event

        if ctx.raw_memories:
            summaries = []
            for mem in ctx.raw_memories[:5]:
                text = mem.get("memory", "")[:80]
                ts = mem.get("updated_at") or mem.get("created_at") or ""
                date_str = ""
                if ts:
                    try:
                        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                        date_str = dt.strftime("%b %Y")
                    except (ValueError, AttributeError):
                        pass
                prefix = f"[{date_str}] " if date_str else ""
                summaries.append(f"{prefix}{text}")
            mem_event = AgentEvent(
                type=AgentEventType.STATUS,
                data={
                    "step": "memory",
                    "message": f"Retrieved {ctx.memories_used} memories",
                    "details": summaries,
                },
            )
            accumulator.record_event(mem_event)
            yield mem_event
        else:
            mem_event = AgentEvent(
                type=AgentEventType.STATUS,
                data={"step": "memory", "message": "No relevant memories found"},
            )
            accumulator.record_event(mem_event)
            yield mem_event

        # 4. Build conversation messages
        messages = await self._build_conversation_messages(
            conversation.id, content, image_parts=image_parts
        )

        # 5. Stream response via AgentCore
        agent_session = AgentSession(
            profile_id=profile.id,
            system_prompt=ctx.system_prompt,
            messages=messages,
        )

        full_content = ""
        async for event in self._agent.run_stream(agent_session, CHAT_AGENT):
            if event.type == AgentEventType.TEXT_DELTA:
                full_content += event.data.get("content", "")
                yield event
            elif event.type == AgentEventType.DONE:
                # Swallow AgentCore's DONE — we emit our own with full metadata.
                # Do NOT override full_content here: it already has the complete
                # text accumulated from all TEXT_DELTA events across all agent
                # rounds. The DONE event's content only has the last round's text.
                pass
            else:
                accumulator.record_event(event)
                yield event

        # 6. Safety validation
        violations = validate_response(full_content)
        full_content = sanitize_response(full_content, violations)

        # 7. Build rich content parts and persist
        image_urls = (
            await upload_images_for_parts(image_parts, profile.id) if image_parts else None
        )
        user_parts = build_user_parts(content, image_urls)
        assistant_parts = build_assistant_parts(full_content, accumulator, ctx)

        user_msg = ChatMessage(
            conversation_id=conversation.id,
            role="user",
            content=content,
            content_parts=user_parts,
        )
        assistant_msg = ChatMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=full_content,
            content_parts=assistant_parts,
        )
        now = datetime.now(timezone.utc)
        user_msg.created_at = now
        assistant_msg.created_at = now + timedelta(milliseconds=1)
        self._db.add_all([user_msg, assistant_msg])
        conversation.updated_at = func.now()
        await self._db.commit()
        await self._db.refresh(user_msg)
        await self._db.refresh(assistant_msg)

        # 8. Yield DONE immediately — client resolves on this event.
        yield AgentEvent(
            type=AgentEventType.DONE,
            data={
                "id": str(assistant_msg.id),
                "user_message_id": str(user_msg.id),
                "conversation_id": str(conversation.id),
                "content": full_content,
                "disclaimer": CHAT_DISCLAIMER,
            },
        )

        # 9. Best-effort topic generation (runs after DONE, client doesn't wait)
        if is_new_conversation and not topic:
            await self._auto_generate_topic(conversation, content)

        await self._log_action(
            profile,
            ActionType.CHAT_MESSAGE,
            {
                "conversation_id": str(conversation.id),
                "topic": conversation.topic,
                "message_preview": content[:100],
            },
        )

    async def get_conversation(
        self,
        conversation_id: UUID,
        profile_id: UUID,
    ) -> ChatConversation | None:
        """Get a conversation by ID, scoped to profile."""
        result = await self._db.execute(
            select(ChatConversation).where(
                ChatConversation.id == conversation_id,
                ChatConversation.profile_id == profile_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_conversations(
        self,
        profile_id: UUID,
        topic: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> PaginatedResponse[ChatConversationResponse]:
        """List chat conversations for a profile."""
        base_query = select(ChatConversation).where(ChatConversation.profile_id == profile_id)
        if topic:
            base_query = base_query.where(ChatConversation.topic.ilike(f"%{topic}%"))

        count_result = await self._db.execute(
            select(func.count()).select_from(base_query.subquery())
        )
        total = count_result.scalar_one()

        result = await self._db.execute(
            base_query.offset((page - 1) * per_page)
            .limit(per_page)
            .order_by(ChatConversation.updated_at.desc())
        )
        conversations = result.scalars().all()

        return PaginatedResponse(
            items=[ChatConversationResponse.model_validate(c) for c in conversations],
            total=total,
            page=page,
            per_page=per_page,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _build_conversation_messages(
        self,
        conversation_id: UUID,
        new_user_message: str,
        image_parts: list[ImagePart] | None = None,
    ) -> list[dict]:
        """Load conversation history, apply sliding window, append new message.

        Note: crisis messages (stored when detect_mental_health_crisis fired)
        are included in history. Subsequent LLM turns will see them, which
        lets the model acknowledge prior distress and respond with appropriate
        care. They are not sent to the LLM without a system prompt that
        frames the assistant as a health advisor.
        """
        # Cap DB fetch to the most recent 100 messages. The token-window
        # filter applied below will further reduce what's sent to the LLM.
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(100)
        )
        result = await self._db.execute(stmt)
        # Rows come back newest-first; reverse so oldest is first for the window
        history = list(reversed(result.scalars().all()))

        messages = [{"role": m.role, "content": m.content} for m in history]

        if messages:
            windowed = build_conversation_window(messages, MAX_HISTORY_TOKENS)
        else:
            windowed = []

        new_msg: dict = {"role": "user", "content": new_user_message}
        if image_parts:
            new_msg["image_parts"] = image_parts
        windowed.append(new_msg)
        return windowed

    async def _auto_generate_topic(
        self,
        conversation: ChatConversation,
        first_message: str,
    ) -> None:
        """Best-effort topic generation via LLM summarization."""
        try:
            prompt = TOPIC_EXTRACTION_PROMPT.format(message=first_message)
            request = LLMRequest(
                task=LLMTask.SUMMARIZATION,
                system_prompt="You generate short topic labels for conversations.",
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.3,
                max_tokens=30,
            )
            response = await self._agent.call(request)
            topic = response.content.strip().strip('"').strip("'")
            if topic and len(topic) <= 100:
                conversation.topic = topic
                await self._db.commit()
        except Exception:
            logger.debug("Topic auto-generation failed, leaving topic as None")

    async def _log_action(
        self,
        profile: Profile,
        action_type: ActionType,
        payload: dict,
    ) -> None:
        """Best-effort action logging."""
        try:
            log_svc = ActionLogService(self._db)
            await log_svc.log(
                profile_id=profile.id,
                account_id=profile.account_id,
                action_type=action_type,
                payload=payload,
            )
        except Exception:
            logger.exception("Action logging failed for %s", action_type)
