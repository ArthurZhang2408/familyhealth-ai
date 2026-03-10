"""DiagnosisService — orchestrates the diagnosis agent feature."""

from __future__ import annotations

import copy
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.core import AgentCore
from app.agents.definitions import DIAGNOSIS_AGENT
from app.agents.session import AgentSession
from app.agents.types import AgentEvent, AgentEventType
from app.models.diagnosis import DiagnosisMessage, DiagnosisSession
from app.models.profile import Profile
from app.schemas.action_log import ActionType
from app.schemas.common import PaginatedResponse
from app.schemas.diagnosis import (
    DiagnosisMessageResponse,
    DiagnosisSessionResponse,
    DiagnosisState,
    DiagnosisTurnResponse,
)
from app.services.action_log import ActionLogService
from app.services.context_builder import ContextBuilder
from app.services.diagnosis_prompts import (
    DIAGNOSIS_SYSTEM_PROMPT,
    FALLBACK_DIAGNOSIS_STATE,
    MEDICAL_DISCLAIMER,
    STATE_EXTRACTION_PROMPT,
)
from app.services.diagnosis_safety import (
    get_emergency_response,
    pre_check_red_flags,
    sanitize_response,
    validate_response,
)
from app.services.llm import ImagePart, LLMMessage, LLMRequest, LLMResponse, LLMTask
from app.services.memory import build_conversation_window
from app.services.memory_extractor import MemoryExtractor
from app.services.memory_trace import record_extraction, record_retrieval
from app.services.message_parts_builder import (
    PartsAccumulator,
    build_assistant_parts,
    build_assistant_parts_from_result,
    build_user_parts,
    upload_images_for_parts,
)

logger = logging.getLogger(__name__)

# Max tokens for conversation history window
MAX_HISTORY_TOKENS = 4000


class DiagnosisService:
    """Orchestrates the diagnosis feature.

    Responsibilities:
    - Session CRUD
    - Prompt assembly and LLM orchestration (two-pass strategy)
    - Response parsing and safety validation
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

    async def create_session_only(
        self,
        profile: Profile,
        chief_complaint: str,
    ) -> DiagnosisSession:
        """Create a diagnosis session record without generating an AI response.

        Used by the streaming flow: create session → navigate → stream first message.
        """
        session = DiagnosisSession(
            profile_id=profile.id,
            chief_complaint=chief_complaint,
            title=chief_complaint,
            status="active",
        )
        self._db.add(session)
        await self._db.commit()
        await self._auto_generate_title(session, chief_complaint)
        return session

    async def create_session(
        self,
        profile: Profile,
        chief_complaint: str,
    ) -> tuple[DiagnosisSession, DiagnosisTurnResponse]:
        """Create a new diagnosis session and generate the first AI response.

        Returns (session, turn_response).
        """
        # Pre-check red flags before creating the session
        profile_age = self._calculate_age(profile)
        red_flags = pre_check_red_flags(chief_complaint, profile_age)

        # Create session
        session = DiagnosisSession(
            profile_id=profile.id,
            chief_complaint=chief_complaint,
            title=chief_complaint,
            status="active",
        )
        self._db.add(session)
        await self._db.flush()

        if red_flags:
            # Emergency short-circuit — use template, skip LLM
            conversation_text, severity = get_emergency_response(red_flags)
            diagnosis_state = DiagnosisState(
                phase="triage",
                turn_number=0,
                severity=severity,
                red_flags_detected=red_flags,
                information_gathered={"chief_complaint": chief_complaint},
            )
        else:
            # Normal flow — call LLM
            conversation_text, diagnosis_state = await self._handle_turn(
                session, profile, chief_complaint
            )

        # Store messages with content parts
        user_parts = build_user_parts(chief_complaint)
        assistant_parts = build_assistant_parts_from_result(conversation_text)

        user_msg = DiagnosisMessage(
            session_id=session.id,
            role="user",
            content=chief_complaint,
            content_parts=user_parts,
        )
        assistant_msg = DiagnosisMessage(
            session_id=session.id,
            role="assistant",
            content=conversation_text,
            content_parts=assistant_parts,
        )
        now = datetime.now(timezone.utc)
        user_msg.created_at = now
        assistant_msg.created_at = now + timedelta(milliseconds=1)
        self._db.add_all([user_msg, assistant_msg])

        # Update session with differential if available
        if diagnosis_state.differential_diagnoses:
            session.differential_diagnoses = [
                d.model_dump() for d in diagnosis_state.differential_diagnoses
            ]

        # Log action
        await self._log_action(
            profile,
            ActionType.DIAGNOSIS_STARTED,
            {
                "session_id": str(session.id),
                "chief_complaint": chief_complaint,
                "severity": diagnosis_state.severity,
                "red_flags": red_flags,
            },
        )

        await self._db.commit()
        await self._db.refresh(user_msg)
        await self._db.refresh(assistant_msg)

        await self._auto_generate_title(session, chief_complaint)

        turn_response = DiagnosisTurnResponse(
            message=DiagnosisMessageResponse.model_validate(assistant_msg),
            diagnosis_state=diagnosis_state,
            disclaimer=MEDICAL_DISCLAIMER,
        )

        return session, turn_response

    async def send_message(
        self,
        session: DiagnosisSession,
        profile: Profile,
        content: str,
        image_parts: list[ImagePart] | None = None,
    ) -> DiagnosisTurnResponse:
        """Send a user message and get the agent's response."""
        if session.status != "active":
            from app.core.exceptions import AppError

            raise AppError(
                status_code=400,
                detail=f"Cannot send messages to a {session.status} session",
                code="SESSION_NOT_ACTIVE",
            )

        # Red flag pre-check
        profile_age = self._calculate_age(profile)
        red_flags = pre_check_red_flags(content, profile_age)

        if red_flags:
            conversation_text, severity = get_emergency_response(red_flags)
            diagnosis_state = DiagnosisState(
                phase="triage",
                severity=severity,
                red_flags_detected=red_flags,
                information_gathered={"chief_complaint": session.chief_complaint},
            )
        else:
            conversation_text, diagnosis_state = await self._handle_turn(
                session, profile, content, image_parts=image_parts
            )

        # Store messages with content parts
        image_urls = (
            await upload_images_for_parts(image_parts, profile.id) if image_parts else None
        )
        user_parts = build_user_parts(content, image_urls)
        assistant_parts = build_assistant_parts_from_result(conversation_text)

        user_msg = DiagnosisMessage(
            session_id=session.id,
            role="user",
            content=content,
            content_parts=user_parts,
        )
        assistant_msg = DiagnosisMessage(
            session_id=session.id,
            role="assistant",
            content=conversation_text,
            content_parts=assistant_parts,
        )
        now = datetime.now(timezone.utc)
        user_msg.created_at = now
        assistant_msg.created_at = now + timedelta(milliseconds=1)
        self._db.add_all([user_msg, assistant_msg])

        # Update session differential
        if diagnosis_state.differential_diagnoses:
            session.differential_diagnoses = [
                d.model_dump() for d in diagnosis_state.differential_diagnoses
            ]

        # Log action
        await self._log_action(
            profile,
            ActionType.DIAGNOSIS_MESSAGE,
            {
                "session_id": str(session.id),
                "turn": diagnosis_state.turn_number,
                "phase": diagnosis_state.phase,
                "severity": diagnosis_state.severity,
            },
        )

        await self._db.commit()
        await self._db.refresh(user_msg)
        await self._db.refresh(assistant_msg)

        return DiagnosisTurnResponse(
            message=DiagnosisMessageResponse.model_validate(assistant_msg),
            diagnosis_state=diagnosis_state,
            disclaimer=MEDICAL_DISCLAIMER,
        )

    async def send_message_stream(
        self,
        profile: Profile,
        content: str,
        session_id: UUID | None = None,
        chief_complaint: str | None = None,
        image_parts: list[ImagePart] | None = None,
        structured_response: dict | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Streaming send_message. Creates session if session_id not provided.

        Mirrors ChatService.send_message_stream() — optional session_id,
        auto-create if missing, emit session_id in an early status event.
        """
        from app.core.exceptions import AppError

        # 1. Resolve or create session
        if session_id:
            session = await self.get_session(session_id, profile.id)
            if not session:
                raise AppError(
                    status_code=404, detail="Diagnosis session not found", code="NOT_FOUND"
                )
        else:
            session = DiagnosisSession(
                profile_id=profile.id,
                chief_complaint=chief_complaint or content,
                title=chief_complaint or content,
                status="active",
            )
            self._db.add(session)
            await self._db.commit()

        if session.status != "active":
            raise AppError(
                status_code=400,
                detail=f"Cannot send messages to a {session.status} session",
                code="SESSION_NOT_ACTIVE",
            )

        # Emit session_id immediately so the client can update its URL
        yield AgentEvent(
            type=AgentEventType.STATUS,
            data={
                "step": "session_created",
                "message": "Starting diagnosis...",
                "session_id": str(session.id),
            },
        )

        # Red flag pre-check
        accumulator = PartsAccumulator()
        ctx = None
        profile_age = self._calculate_age(profile)
        red_flags = pre_check_red_flags(content, profile_age)

        if red_flags:
            conversation_text, severity = get_emergency_response(red_flags)
            diagnosis_state = DiagnosisState(
                phase="triage",
                severity=severity,
                red_flags_detected=red_flags,
                information_gathered={"chief_complaint": session.chief_complaint},
            )
            yield AgentEvent(
                type=AgentEventType.TEXT_DELTA,
                data={"content": conversation_text},
            )
        else:
            # Stream the main agent response (Pass 1)
            ctx_event = AgentEvent(
                type=AgentEventType.STATUS,
                data={"step": "context", "message": "Loading patient context..."},
            )
            accumulator.record_event(ctx_event)
            yield ctx_event

            ctx = await self._ctx.build(
                db=self._db,
                profile_id=profile.id,
                query=session.chief_complaint,
                interaction_type="diagnosis",
                memory_budget=2000,
                template=DIAGNOSIS_SYSTEM_PROMPT,
            )
            system_prompt = ctx.system_prompt

            # Record memory retrieval trace
            await record_retrieval(
                self._db,
                profile_id=profile.id,
                session_type="diagnosis",
                session_id=session.id,
                turn_number=None,  # set after building messages below
                query=session.chief_complaint,
                raw_memories=ctx.raw_memories or [],
                injected_count=ctx.memories_used,
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

            messages = await self._build_conversation_messages(
                session.id, content, image_parts=image_parts
            )
            turn_number = sum(1 for m in messages if m["role"] == "user")
            system_prompt = system_prompt.replace("{turn_number}", str(turn_number))

            # Snapshot conversation history before agent loop mutates it
            debug_history_snapshot = [
                {"role": m["role"], "content": m["content"]}
                for m in messages
            ]

            agent_session = AgentSession(
                profile_id=profile.id,
                system_prompt=system_prompt,
                messages=messages,
            )

            conversation_text = ""
            debug_rounds: list[dict] = []
            async for event in self._agent.run_stream(agent_session, DIAGNOSIS_AGENT):
                if event.type == AgentEventType.TEXT_DELTA:
                    conversation_text += event.data.get("content", "")
                    yield event
                elif event.type == AgentEventType.DONE:
                    done_content = event.data.get("content", "")
                    if done_content:
                        conversation_text = done_content
                    debug_rounds = event.data.get("debug_rounds", [])
                elif event.type == AgentEventType.TOOL_RESULT:
                    accumulator.record_event(event)
                    yield event
                    # Emit structured question for present_question tool results
                    if event.data.get("tool") == "present_question":
                        # Use the last present_question tool call's args
                        pq_calls = [
                            tc for tc in accumulator.tool_calls
                            if tc.name == "present_question"
                        ]
                        if pq_calls:
                            tc = pq_calls[-1]
                            yield AgentEvent(
                                type=AgentEventType.STRUCTURED_QUESTION,
                                data={
                                    "input_type": tc.arguments.get("input_type"),
                                    "prompt": tc.arguments.get("prompt"),
                                    "options": tc.arguments.get("options"),
                                    "range": tc.arguments.get("range"),
                                },
                            )
                else:
                    accumulator.record_event(event)
                    yield event

            # Safety validation
            violations = validate_response(conversation_text)
            conversation_text = sanitize_response(conversation_text, violations)

        # Build rich content parts and persist messages immediately
        image_urls = (
            await upload_images_for_parts(image_parts, profile.id) if image_parts else None
        )
        user_parts = build_user_parts(content, image_urls, structured_response)
        assistant_parts = build_assistant_parts(conversation_text, accumulator, ctx)

        # Build debug metadata — records what the agent saw and did
        debug_metadata = None
        if not red_flags:
            # Build enriched history with thinking stripped for readability
            enriched_preview = []
            for m in debug_history_snapshot:
                c = m["content"]
                # Strip [Thinking: ...] prefix to show the actual content
                if c.startswith("[Thinking:"):
                    # Find the end of the thinking block
                    end = c.find("]\n")
                    actual = c[end + 2:].strip() if end != -1 else c
                    enriched_preview.append({
                        "role": m["role"],
                        "content": actual[:300] if actual else "(thinking only)",
                        "has_thinking": True,
                    })
                else:
                    enriched_preview.append({
                        "role": m["role"],
                        "content": c[:300],
                    })

            debug_metadata = {
                "turn_number": turn_number,
                "enriched_history": enriched_preview,
                "agent_rounds": debug_rounds,
                "memories_used": ctx.memories_used,
            }

        user_msg = DiagnosisMessage(
            session_id=session.id,
            role="user",
            content=content,
            content_parts=user_parts,
        )
        assistant_msg = DiagnosisMessage(
            session_id=session.id,
            role="assistant",
            content=conversation_text,
            content_parts=assistant_parts,
            metadata_=debug_metadata,
        )
        now = datetime.now(timezone.utc)
        user_msg.created_at = now
        assistant_msg.created_at = now + timedelta(milliseconds=1)
        self._db.add_all([user_msg, assistant_msg])

        # Red flags → triage state; normal → fallback (real extraction after DONE)
        done_state = (
            diagnosis_state if red_flags
            else DiagnosisState.model_validate(copy.deepcopy(FALLBACK_DIAGNOSIS_STATE))
        )

        await self._db.commit()
        await self._db.refresh(user_msg)
        await self._db.refresh(assistant_msg)

        # Yield DONE immediately — client resolves on this
        yield AgentEvent(
            type=AgentEventType.DONE,
            data={
                "content": conversation_text,
                "session_id": str(session.id),
                "id": str(assistant_msg.id),
                "user_message_id": str(user_msg.id),
                "diagnosis_state": done_state.model_dump(),
                "disclaimer": MEDICAL_DISCLAIMER,
            },
        )

        # Best-effort post-processing: state extraction + memory extraction + logging
        if not red_flags:
            try:
                diagnosis_state = await self._extract_state(
                    system_prompt, messages, conversation_text
                )
                if diagnosis_state.differential_diagnoses:
                    session.differential_diagnoses = [
                        d.model_dump() for d in diagnosis_state.differential_diagnoses
                    ]
                await self._db.commit()
            except Exception:
                logger.warning("Post-DONE state extraction failed", exc_info=True)

            # Extract session facts to long-term memory when an assessment
            # is delivered.  Uses a stable source key so Mem0 UPDATEs existing
            # memories on follow-up assessments instead of creating duplicates.
            if "## Assessment" in conversation_text:
                try:
                    await self._extract_assessment_memories(
                        session, profile, messages, conversation_text, turn_number,
                    )
                except Exception:
                    logger.warning(
                        "Assessment memory extraction failed for session %s",
                        session.id,
                        exc_info=True,
                    )

        await self._log_action(
            profile,
            ActionType.DIAGNOSIS_MESSAGE,
            {
                "session_id": str(session.id),
                "turn": diagnosis_state.turn_number,
                "phase": diagnosis_state.phase,
                "severity": diagnosis_state.severity,
            },
        )

    async def get_session(
        self,
        session_id: UUID,
        profile_id: UUID,
    ) -> DiagnosisSession | None:
        """Get a session by ID, scoped to profile."""
        result = await self._db.execute(
            select(DiagnosisSession).where(
                DiagnosisSession.id == session_id,
                DiagnosisSession.profile_id == profile_id,
            )
        )
        return result.scalar_one_or_none()

    async def close_session(
        self,
        session: DiagnosisSession,
        profile: Profile,
        resolution_notes: str | None = None,
    ) -> DiagnosisSession:
        """Resolve a diagnosis session and extract resolution memories."""
        if session.status != "active":
            from app.core.exceptions import AppError

            raise AppError(
                status_code=400,
                detail=f"Cannot close a {session.status} session",
                code="SESSION_NOT_ACTIVE",
            )

        session.status = "resolved"
        session.resolved_at = func.now()
        session.resolution_notes = resolution_notes

        # Build resolution summary for memory extraction
        summary_parts = [
            f"Diagnosis session resolved for chief complaint: {session.chief_complaint}.",
        ]
        if session.differential_diagnoses:
            top = session.differential_diagnoses[0]
            summary_parts.append(
                f"Top assessment: {top.get('condition', 'unknown')} "
                f"(confidence: {top.get('confidence', 'N/A')})."
            )
        if resolution_notes:
            summary_parts.append(f"Outcome: {resolution_notes}")

        resolution_summary = " ".join(summary_parts)

        # Extract resolution facts to long-term memory (best-effort).
        # Uses our own LLM (Cerebras/Qwen) instead of Mem0's internal LLM.
        try:
            facts = await self._llm_extract_facts(resolution_summary)
            if facts:
                extraction_result = await self._mem_extractor.store_facts(
                    profile_id=profile.id,
                    facts=facts,
                    source=f"diagnosis:{session.id}:resolution",
                    category="diagnoses",
                )
                await record_extraction(
                    self._db,
                    profile_id=profile.id,
                    session_type="diagnosis",
                    session_id=session.id,
                    mem0_result=extraction_result,
                    input_message_count=1,
                )
        except Exception:
            logger.exception("Resolution memory extraction failed for session %s", session.id)

        # Log action
        await self._log_action(
            profile,
            ActionType.DIAGNOSIS_RESOLVED,
            {
                "session_id": str(session.id),
                "chief_complaint": session.chief_complaint,
                "differential": session.differential_diagnoses,
                "resolution_notes": resolution_notes,
            },
        )

        await self._db.flush()
        return session

    async def list_sessions(
        self,
        profile_id: UUID,
        status: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> PaginatedResponse[DiagnosisSessionResponse]:
        """List diagnosis sessions for a profile."""
        base_query = select(DiagnosisSession).where(DiagnosisSession.profile_id == profile_id)
        if status:
            base_query = base_query.where(DiagnosisSession.status == status)

        count_result = await self._db.execute(
            select(func.count()).select_from(base_query.subquery())
        )
        total = count_result.scalar_one()

        result = await self._db.execute(
            base_query.offset((page - 1) * per_page)
            .limit(per_page)
            .order_by(DiagnosisSession.created_at.desc())
        )
        sessions = result.scalars().all()

        return PaginatedResponse(
            items=[DiagnosisSessionResponse.model_validate(s) for s in sessions],
            total=total,
            page=page,
            per_page=per_page,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _handle_turn(
        self,
        session: DiagnosisSession,
        profile: Profile,
        user_content: str,
        image_parts: list[ImagePart] | None = None,
    ) -> tuple[str, DiagnosisState]:
        """Process a single turn: context -> LLM Pass 1 -> safety -> Pass 2."""
        # 1. Build context via ContextBuilder
        ctx = await self._ctx.build(
            db=self._db,
            profile_id=profile.id,
            query=user_content,
            interaction_type="diagnosis",
            memory_budget=2000,
            template=DIAGNOSIS_SYSTEM_PROMPT,
        )
        system_prompt = ctx.system_prompt

        # 2. Build conversation messages with sliding window
        messages = await self._build_conversation_messages(
            session.id, user_content, image_parts=image_parts
        )

        # Inject turn number — count user messages in history + the new one
        turn_number = sum(1 for m in messages if m["role"] == "user")
        system_prompt = system_prompt.replace("{turn_number}", str(turn_number))

        # 3. Pass 1 — Generate conversational response via AgentCore
        agent_session = AgentSession(
            profile_id=profile.id,
            system_prompt=system_prompt,
            messages=messages,
        )
        agent_result = await self._agent.run(agent_session, DIAGNOSIS_AGENT)
        conversation_text = agent_result.content.strip()

        # 4. Safety validation
        violations = validate_response(conversation_text)
        conversation_text = sanitize_response(conversation_text, violations)

        # 5. Pass 2 — Extract structured diagnosis state
        diagnosis_state = await self._extract_state(system_prompt, messages, conversation_text)

        return conversation_text, diagnosis_state

    async def _build_conversation_messages(
        self,
        session_id: UUID,
        new_user_message: str,
        image_parts: list[ImagePart] | None = None,
    ) -> list[dict]:
        """Load session history, apply sliding window, append new message."""
        stmt = (
            select(DiagnosisMessage)
            .where(DiagnosisMessage.session_id == session_id)
            .order_by(DiagnosisMessage.created_at)
        )
        result = await self._db.execute(stmt)
        history = result.scalars().all()

        messages = [
            {"role": m.role, "content": self._enrich_content(m)}
            for m in history
        ]

        # Apply sliding window: keep first message (chief complaint) + fill from recent
        if messages:
            windowed = build_conversation_window(messages, MAX_HISTORY_TOKENS)
        else:
            windowed = []

        # Append the new user message
        new_msg: dict = {"role": "user", "content": new_user_message}
        if image_parts:
            new_msg["image_parts"] = image_parts
        windowed.append(new_msg)

        return windowed

    @staticmethod
    def _enrich_content(msg: DiagnosisMessage) -> str:
        """Enrich message content with structured question/answer data.

        The LLM only sees plain text in conversation history. Without this,
        the agent has no idea what questions it asked (they're in content_parts)
        and repeats itself.

        Also surfaces web search results and thinking content so context
        persists across turns.
        """
        content = msg.content or ""
        if not msg.content_parts:
            return content

        parts_list = msg.content_parts
        if not isinstance(parts_list, list):
            return content

        extras: list[str] = []

        # --- Recover empty assistant messages (tool calls with no text) ---
        if msg.role == "assistant" and not content.strip():
            for part in parts_list:
                if (
                    isinstance(part, dict)
                    and part.get("type") == "tool_call"
                    and part.get("name") == "present_question"
                ):
                    question = (part.get("arguments") or {}).get("prompt", "")
                    if question:
                        content = question
                    break

        for part in parts_list:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")

            # --- Structured input enrichment (user messages only) ---
            if ptype == "structured_input" and msg.role == "user" and part.get("selected") is not None:
                prompt = part.get("prompt", "")
                options = part.get("options") or []
                input_type = part.get("input_type", "")
                opt_labels = [o.get("label", "") for o in options if isinstance(o, dict)]

                if input_type == "multi_select":
                    # Prepend question, keep the Has/Does NOT have from content
                    ctx = f'(Q: "{prompt}")\n'
                    content = ctx + content
                else:
                    # multiple_choice, yes_no, scale — keep options listing
                    ctx = f'(Q: "{prompt}"'
                    if opt_labels:
                        ctx += f" — options: {', '.join(opt_labels)}"
                    ctx += ")\n"
                    content = ctx + content

            # --- Web search results (assistant messages) ---
            elif ptype == "tool_result" and msg.role == "assistant":
                tool_name = part.get("name", "")
                output = part.get("output")
                if tool_name == "web_search" and isinstance(output, dict):
                    results = output.get("results") or []
                    if results:
                        snippets = "; ".join(
                            f"{r.get('title', '')}: {r.get('snippet', '')}"
                            for r in results[:5]
                            if isinstance(r, dict)
                        )
                        extras.append(f"[Prior web search results: {snippets}]")

            # --- Thinking content (assistant messages) ---
            elif ptype == "thinking" and msg.role == "assistant":
                thinking_text = part.get("text", "")
                if thinking_text:
                    extras.append(f"[Thinking: {thinking_text}]")

        if extras:
            content = "\n".join(extras) + "\n" + content

        return content

    async def _extract_state(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        assistant_response: str,
    ) -> DiagnosisState:
        """Pass 2: Extract structured DiagnosisState via JSON-mode LLM call.

        Uses FACT_EXTRACTION task (routes to Qwen) with JSON mode.
        Falls back to a minimal state on failure.
        """
        try:
            all_messages = messages + [
                {"role": "assistant", "content": assistant_response},
                {"role": "user", "content": STATE_EXTRACTION_PROMPT},
            ]

            request = LLMRequest(
                task=LLMTask.FACT_EXTRACTION,
                system_prompt=system_prompt,
                messages=[LLMMessage(role=m["role"], content=m["content"]) for m in all_messages],
                temperature=0.0,
                max_tokens=2000,
                response_format={"type": "json"},
            )
            response: LLMResponse = await self._agent.call(request)
            raw_state = json.loads(response.content)

            return DiagnosisState.model_validate(raw_state)

        except Exception:
            logger.warning(
                "Pass 2 state extraction failed, using fallback",
                exc_info=True,
            )
            fallback = copy.deepcopy(FALLBACK_DIAGNOSIS_STATE)
            return DiagnosisState.model_validate(fallback)

    async def _extract_assessment_memories(
        self,
        session: DiagnosisSession,
        profile: Profile,
        messages: list[dict],
        assessment_text: str,
        turn_number: int,
    ) -> None:
        """Extract session facts to long-term memory on assessment delivery.

        Bypasses Mem0's internal LLM (which produces poor-quality extractions)
        and uses our own LLM (Cerebras → Qwen fallback) to extract discrete
        facts, then stores them directly via ``infer=False``.

        Uses a stable source key (``diagnosis:<sid>``) so that follow-up
        assessments within the same session can be traced to the same source.
        """
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")

        # Count previous assessments to determine if this is a follow-up
        prev_assessments = sum(
            1
            for m in messages
            if m["role"] == "assistant" and "## Assessment" in m.get("content", "")
        )
        is_followup = prev_assessments > 0

        # Build a concise summary from user messages
        reported: list[str] = []
        for m in messages:
            if m["role"] != "user":
                continue
            content = m.get("content", "").strip()
            if not content or content == session.chief_complaint:
                continue
            reported.append(content)

        # Count turns since last assessment (or from start)
        prev_turn = 0
        for m in messages:
            if m["role"] == "assistant" and "## Assessment" in m.get("content", ""):
                prev_turn = sum(1 for msg in messages[:messages.index(m) + 1] if msg["role"] == "user")

        if is_followup:
            header = f"Follow-up assessment on {date_str} (turns {prev_turn + 1}–{turn_number})."
        else:
            header = f"Initial assessment on {date_str} (turns 1–{turn_number})."

        # Extract just the assessment section, not the full response
        assessment_start = assessment_text.find("## Assessment")
        assessment_section = assessment_text[assessment_start:assessment_start + 2000] if assessment_start >= 0 else assessment_text[:2000]

        summary = (
            f"{header}\n"
            f"Chief complaint: {session.chief_complaint}.\n"
            f"Patient reported: {'; '.join(reported)}.\n"
            f"Assessment:\n{assessment_section}"
        )

        # Use our own LLM to extract discrete facts (not Mem0's nemotron)
        facts = await self._llm_extract_facts(summary)
        if not facts:
            logger.warning("No facts extracted for session %s", session.id)
            return

        extraction_result = await self._mem_extractor.store_facts(
            profile_id=profile.id,
            facts=facts,
            source=f"diagnosis:{session.id}",
            category="symptoms",
        )
        await record_extraction(
            self._db,
            profile_id=profile.id,
            session_type="diagnosis",
            session_id=session.id,
            mem0_result=extraction_result,
            input_message_count=1,
        )
        logger.info(
            "Assessment memory extraction for session %s (%s, turn %d): %d facts",
            session.id,
            "follow-up" if is_followup else "initial",
            turn_number,
            len(facts),
        )

    async def _llm_extract_facts(self, summary: str) -> list[str]:
        """Use Cerebras/Qwen to extract discrete medical facts from a session summary.

        Returns a list of short, factual statements suitable for memory storage.
        """
        prompt = (
            "Extract discrete medical facts from this diagnosis session summary. "
            "Return ONLY a JSON array of short factual strings. Each fact should be "
            "a single, specific observation — not a recommendation or instruction.\n\n"
            "Good examples:\n"
            '- "Upper abdominal cramping pain, severity 4/10, started 2026-03-10"\n'
            '- "Pain worsens after eating"\n'
            '- "No nausea, vomiting, diarrhea, or fever"\n'
            '- "Assessed as acute gastritis"\n'
            '- "No NSAID or alcohol use"\n\n'
            "Bad examples (do NOT produce these):\n"
            '- "Recommend antacids" (instruction, not fact)\n'
            '- "No recent changes in diet" (hallucinated negation)\n\n'
            f"Session summary:\n{summary}"
        )
        request = LLMRequest(
            task=LLMTask.FACT_EXTRACTION,
            system_prompt="You are a medical fact extractor. Output only a JSON array of strings.",
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.0,
            max_tokens=1000,
            response_format={"type": "json"},
        )
        response: LLMResponse = await self._agent.call(request)
        try:
            parsed = json.loads(response.content)
            if isinstance(parsed, list):
                return [str(f) for f in parsed if isinstance(f, str) and f.strip()]
            # Handle {"facts": [...]} wrapper
            if isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, list):
                        return [str(f) for f in v if isinstance(f, str) and f.strip()]
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse fact extraction response: %s", response.content[:200])
        return []

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

    async def _auto_generate_title(
        self,
        session: DiagnosisSession,
        chief_complaint: str,
    ) -> None:
        """Best-effort title generation via LLM summarization."""
        try:
            prompt = (
                "Generate a very short topic label (3-6 words) for a medical diagnosis session "
                "that started with this chief complaint. Return ONLY the topic text, nothing else.\n\n"
                "Examples:\n"
                '- "I have a bad headache that won\'t go away" → "Persistent headache"\n'
                '- "My knee hurts when I walk up stairs" → "Knee pain on stairs"\n'
                '- "I\'ve been coughing for two weeks" → "Persistent cough"\n'
                '- "Feeling dizzy and nauseous since yesterday" → "Dizziness and nausea"\n\n'
                f"Chief complaint: {chief_complaint}"
            )
            request = LLMRequest(
                task=LLMTask.SUMMARIZATION,
                system_prompt="You generate short topic labels for medical sessions.",
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.3,
                max_tokens=30,
            )
            response = await self._agent.call(request)
            title = response.content.strip().strip('"').strip("'")
            if title and len(title) <= 100:
                session.title = title
                await self._db.commit()
        except Exception:
            logger.debug("Title auto-generation failed for session %s", session.id)

    @staticmethod
    def _calculate_age(profile: Profile) -> float | None:
        """Calculate age from date_of_birth, returning None if unavailable."""
        if not profile.date_of_birth:
            return None
        from datetime import date

        today = date.today()
        age = (
            today.year
            - profile.date_of_birth.year
            - ((today.month, today.day) < (profile.date_of_birth.month, profile.date_of_birth.day))
        )
        return float(age)
