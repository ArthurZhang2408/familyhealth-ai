"""ChatService — orchestrates the general health chat feature."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.core import AgentCore
from app.agents.definitions import CHAT_AGENT
from app.agents.session import AgentSession
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
from app.services.llm import LLMMessage, LLMRequest, LLMTask
from app.services.memory import build_conversation_window
from app.services.memory_extractor import MemoryExtractor

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
            user_msg = ChatMessage(conversation_id=conversation.id, role="user", content=content)
            assistant_msg = ChatMessage(
                conversation_id=conversation.id, role="assistant", content=crisis_text
            )
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
        messages = await self._build_conversation_messages(conversation.id, content)

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

        # 7. Store messages — flush first so they are persisted regardless of
        # what happens in the best-effort steps below (topic generation, logging).
        user_msg = ChatMessage(conversation_id=conversation.id, role="user", content=content)
        assistant_msg = ChatMessage(
            conversation_id=conversation.id, role="assistant", content=response_text
        )
        self._db.add_all([user_msg, assistant_msg])
        conversation.updated_at = func.now()
        await self._db.flush()
        await self._db.refresh(assistant_msg)

        # 8. Auto-generate topic for new conversations (best-effort, after flush)
        if is_new_conversation and not topic:
            await self._auto_generate_topic(conversation, content)

        # 9. Log action
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
    ) -> list[dict[str, str]]:
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

        windowed.append({"role": "user", "content": new_user_message})
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
