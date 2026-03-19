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
    DifferentialDiagnosis,
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
from app.services.llm_trace import record_llm_traces
from app.services.memory import build_conversation_window
from app.services.memory_extractor import MemoryExtractor
from app.services.memory_trace import record_extraction
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


# Confidence display labels used by _format_assessment_text
_CONFIDENCE_LABELS = {
    "most_likely": "Most likely",
    "possible": "Also possible",
    "less_likely": "Less likely but worth checking",
}


def _format_assessment_text(args: dict) -> str:
    """Format present_assessment tool args into markdown for the content column.

    This produces the same markdown shape the agent used to write by hand,
    ensuring backward compatibility for search and old clients.
    """
    sections: list[str] = ["## Assessment\n"]

    for cond in args.get("conditions", []):
        label = _CONFIDENCE_LABELS.get(cond.get("confidence", ""), cond.get("confidence", ""))
        sections.append(f"### {label}: {cond.get('name', '')}\n")
        sections.append(cond.get("reasoning", ""))
        if cond.get("confirming_tests"):
            sections.append(f"\n**What would confirm this:** {cond['confirming_tests']}")
        sections.append("")

    meds = args.get("medications", [])
    self_care = args.get("self_care", [])
    if meds or self_care:
        sections.append("---\n\n## What You Can Do Now\n")
        for med in meds:
            line = f"- **{med.get('name', '')}** {med.get('dosage', '')}"
            if med.get("notes"):
                line += f" — {med['notes']}"
            sections.append(line)
        for sc in self_care:
            line = f"- {sc.get('action', '')}"
            if sc.get("detail"):
                line += f" — {sc['detail']}"
            sections.append(line)
        sections.append("")

    tests = args.get("tests", [])
    if tests:
        sections.append("## Tests to Consider\n")
        for t in tests:
            line = f"- **{t.get('name', '')}** — {t.get('reason', '')}"
            if t.get("urgency"):
                line += f" ({t['urgency']})"
            sections.append(line)
        sections.append("")

    warnings = args.get("warnings", [])
    if warnings:
        sections.append("## Watch For (seek immediate care if)\n")
        for w in warnings:
            sections.append(f"- {w}")
        sections.append("")

    follow_up = args.get("follow_up")
    if follow_up:
        sections.append(f"## Follow-up\n\n{follow_up}\n")

    sources = args.get("sources", [])
    if sources:
        sections.append("---\n\n**Sources:**")
        for i, s in enumerate(sources, 1):
            sections.append(f"{i}. {s.get('title', '')} — {s.get('url', '')}")
        sections.append("")

    return "\n".join(sections)


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
        is_new_session = not session_id
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

            # Profile only — no auto memory retrieval.
            # The agent has search_patient_memory tool and queries on demand.
            ctx = await self._ctx.build(
                db=self._db,
                profile_id=profile.id,
                query=session.chief_complaint,
                interaction_type="diagnosis",
                memory_budget=2000,
                template=DIAGNOSIS_SYSTEM_PROMPT,
                skip_memories=True,
            )
            system_prompt = ctx.system_prompt

            # Emit profile loaded status
            profile_name = ctx.profile_context.get("name", "patient")
            profile_event = AgentEvent(
                type=AgentEventType.STATUS,
                data={"step": "profile", "message": f"Loaded profile for {profile_name}"},
            )
            accumulator.record_event(profile_event)
            yield profile_event

            # Memory retrieval is agent-driven (search_patient_memory tool).
            # No auto-retrieval status events — the agent's tool calls
            # appear in agent steps naturally, like web_search.

            messages = await self._build_conversation_messages(
                session.id, content, image_parts=image_parts
            )
            turn_number = sum(1 for m in messages if m["role"] == "user")
            system_prompt = system_prompt.replace("{turn_number}", str(turn_number))

            # Snapshot conversation history before agent loop mutates it
            debug_history_snapshot = [
                {"role": m["role"], "content": m["content"]} for m in messages
            ]

            agent_session = AgentSession(
                profile_id=profile.id,
                system_prompt=system_prompt,
                messages=messages,
                metadata={"source": f"diagnosis:{session.id}:agent"},
            )

            conversation_text = ""
            debug_rounds: list[dict] = []
            llm_traces: list[dict] = []
            has_assessment_tool = False
            assessment_tool_args: dict = {}
            async for event in self._agent.run_stream(agent_session, DIAGNOSIS_AGENT):
                if event.type == AgentEventType.TEXT_DELTA:
                    conversation_text += event.data.get("content", "")
                    yield event
                elif event.type == AgentEventType.DONE:
                    done_content = event.data.get("content", "")
                    if done_content:
                        conversation_text = done_content
                    debug_rounds = event.data.get("debug_rounds", [])
                    llm_traces = event.data.get("llm_traces", [])
                elif event.type == AgentEventType.TOOL_RESULT:
                    accumulator.record_event(event)
                    yield event
                    tool_name = event.data.get("tool")
                    # Emit structured question for present_question tool results
                    if tool_name == "present_question":
                        pq_calls = [
                            tc for tc in accumulator.tool_calls if tc.name == "present_question"
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
                    # Emit structured assessment for present_assessment tool results
                    elif tool_name == "present_assessment":
                        pa_calls = [
                            tc for tc in accumulator.tool_calls if tc.name == "present_assessment"
                        ]
                        if pa_calls:
                            assessment_tool_args = pa_calls[-1].arguments
                            has_assessment_tool = True
                            # Format as markdown for the content column
                            conversation_text = _format_assessment_text(assessment_tool_args)
                            yield AgentEvent(
                                type=AgentEventType.STRUCTURED_ASSESSMENT,
                                data=assessment_tool_args,
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
                    actual = c[end + 2 :].strip() if end != -1 else c
                    enriched_preview.append(
                        {
                            "role": m["role"],
                            "content": actual[:300] if actual else "(thinking only)",
                            "has_thinking": True,
                        }
                    )
                else:
                    enriched_preview.append(
                        {
                            "role": m["role"],
                            "content": c[:300],
                        }
                    )

            debug_metadata = {
                "turn_number": turn_number,
                "enriched_history": enriched_preview,
                "agent_rounds": debug_rounds,
                "memories_used": (
                    sum(
                        1
                        for tr in accumulator.tool_results
                        if tr.name == "search_patient_memory" and not tr.is_error
                        for _ in tr.output.get("memories", [])
                    )
                    if accumulator
                    else 0
                ),
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
            diagnosis_state
            if red_flags
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
            if has_assessment_tool:
                # Build DiagnosisState directly from the structured tool output
                # — no need for a separate LLM _extract_state() call.
                try:
                    diagnosis_state = self._state_from_assessment_tool(
                        assessment_tool_args, turn_number
                    )
                    session.differential_diagnoses = [
                        d.model_dump() for d in diagnosis_state.differential_diagnoses
                    ]
                    await self._db.commit()
                except Exception:
                    logger.warning("Assessment tool state extraction failed", exc_info=True)
            else:
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

            # Store a single consolidated narrative to long-term memory when
            # an assessment is delivered.  Uses delete-then-add (upsert) so
            # follow-up assessments cleanly replace the previous narrative.
            if has_assessment_tool or "## Assessment" in conversation_text:
                try:
                    await self._store_session_narrative(
                        session,
                        profile,
                        messages,
                        assessment_tool_args,
                    )
                except Exception:
                    logger.warning(
                        "Session narrative storage failed for session %s",
                        session.id,
                        exc_info=True,
                    )

        # Persist LLM traces (best-effort)
        if llm_traces:
            await record_llm_traces(
                self._db,
                session_type="diagnosis",
                session_id=session.id,
                turn_index=turn_number,
                traces=llm_traces,
            )

        # Best-effort title generation for new sessions
        if is_new_session:
            await self._auto_generate_title(session, session.chief_complaint)

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

        # Build a resolution narrative and upsert to long-term memory.
        # Replaces any earlier assessment narrative for the same session.
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")

        narrative_parts = [
            f"Diagnosis session on {date_str} for: {session.chief_complaint}.",
        ]
        if session.differential_diagnoses:
            top = session.differential_diagnoses[0]
            narrative_parts.append(
                f"Assessment: {top.get('condition', top.get('name', 'unknown'))} "
                f"({top.get('confidence', 'N/A')})."
            )
        if resolution_notes:
            narrative_parts.append(f"Resolved — {resolution_notes}.")

        narrative = " ".join(narrative_parts)

        try:
            extraction_result = await self._mem_extractor.store_narrative(
                profile_id=profile.id,
                narrative=narrative,
                source=f"diagnosis:{session.id}:narrative",
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
            logger.exception("Resolution narrative storage failed for session %s", session.id)

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
        # 1. Build context — profile only, agent searches memory on demand
        ctx = await self._ctx.build(
            db=self._db,
            profile_id=profile.id,
            query=user_content,
            interaction_type="diagnosis",
            memory_budget=2000,
            template=DIAGNOSIS_SYSTEM_PROMPT,
            skip_memories=True,
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
            metadata={"source": f"diagnosis:{session.id}:agent"},
        )
        agent_result = await self._agent.run(agent_session, DIAGNOSIS_AGENT)
        conversation_text = agent_result.content.strip()

        # Persist LLM traces (best-effort)
        if agent_result.llm_traces:
            await record_llm_traces(
                self._db,
                session_type="diagnosis",
                session_id=session.id,
                turn_index=turn_number,
                traces=agent_result.llm_traces,
            )

        # 4. Safety validation
        violations = validate_response(conversation_text)
        conversation_text = sanitize_response(conversation_text, violations)

        # 5. Extract structured diagnosis state
        # If present_assessment was called, build state directly from tool args
        pa_calls = [tc for tc in agent_result.tool_calls_made if tc.name == "present_assessment"]
        if pa_calls:
            assessment_args = pa_calls[-1].arguments
            conversation_text = _format_assessment_text(assessment_args)
            diagnosis_state = self._state_from_assessment_tool(assessment_args, turn_number)
        else:
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

        messages = [{"role": m.role, "content": self._enrich_content(m)} for m in history]

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
            if (
                ptype == "structured_input"
                and msg.role == "user"
                and part.get("selected") is not None
            ):
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

    @staticmethod
    def _state_from_assessment_tool(args: dict, turn_number: int) -> DiagnosisState:
        """Build DiagnosisState directly from present_assessment tool arguments.

        Avoids a separate LLM call for state extraction when the agent
        has already provided structured assessment data via the tool.
        """
        confidence_to_score = {
            "most_likely": 0.8,
            "possible": 0.5,
            "less_likely": 0.2,
        }
        confidence_to_urgency = {
            "most_likely": "see_doctor_this_week",
            "possible": "see_doctor_soon",
            "less_likely": "monitor_at_home",
        }
        differentials = []
        for cond in args.get("conditions", []):
            conf_key = cond.get("confidence", "possible")
            differentials.append(
                DifferentialDiagnosis(
                    condition=cond.get("name", ""),
                    confidence=confidence_to_score.get(conf_key, 0.5),
                    reasoning=cond.get("reasoning", ""),
                    action_plan=cond.get("confirming_tests", ""),
                    urgency=confidence_to_urgency.get(conf_key, "see_doctor_soon"),
                )
            )
        return DiagnosisState(
            phase="differential",
            turn_number=turn_number,
            severity="moderate",
            differential_diagnoses=differentials,
            ready_for_differential=True,
        )

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
                max_tokens=4000,
                response_format={"type": "json"},
                extra={"reasoning_effort": "low", "think": False},
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

    async def _store_session_narrative(
        self,
        session: DiagnosisSession,
        profile: Profile,
        messages: list[dict],
        assessment_tool_args: dict,
    ) -> None:
        """Store a single consolidated narrative to long-term memory.

        Replaces per-fact extraction with one narrative paragraph per session.
        Uses delete-then-add (upsert) so follow-up assessments cleanly replace
        the previous narrative instead of accumulating duplicates.
        """
        narrative = await self._build_session_narrative(session, messages, assessment_tool_args)
        if not narrative:
            # Fallback: build bullet points directly from structured data
            logger.warning("LLM narrative empty for session %s, using fallback", session.id)
            narrative = self._build_fallback_narrative(session, messages, assessment_tool_args)
        if not narrative:
            logger.warning("Empty narrative for session %s", session.id)
            return

        extraction_result = await self._mem_extractor.store_narrative(
            profile_id=profile.id,
            narrative=narrative,
            source=f"diagnosis:{session.id}",
        )
        await record_extraction(
            self._db,
            profile_id=profile.id,
            session_type="diagnosis",
            session_id=session.id,
            mem0_result=extraction_result,
            input_message_count=len([m for m in messages if m["role"] == "user"]),
        )
        logger.info("Session narrative stored for session %s", session.id)

    async def _build_session_narrative(
        self,
        session: DiagnosisSession,
        messages: list[dict],
        assessment_tool_args: dict,
    ) -> str:
        """Build a consolidated narrative paragraph via LLM summarization.

        Combines patient Q&A answers and structured assessment data into a
        single factual paragraph suitable for long-term memory storage and
        semantic retrieval.
        """
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")

        # Collect user-reported information (strip enrichment prefixes)
        reported: list[str] = []
        for m in messages:
            if m["role"] != "user":
                continue
            content = m.get("content", "").strip()
            if not content:
                continue
            # Strip Q&A enrichment prefix if present: "(Q: ...) actual answer"
            if content.startswith("(Q:"):
                paren_end = content.find(")")
                if paren_end != -1:
                    content = content[paren_end + 1 :].strip()
            if content:
                reported.append(content)

        # Build assessment summary from structured tool args
        assessment_lines: list[str] = []
        if assessment_tool_args:
            for cond in assessment_tool_args.get("conditions", []):
                name = cond.get("name", "unknown")
                confidence = cond.get("confidence", "")
                assessment_lines.append(f"- {name} ({confidence})")
        else:
            assessment_lines.append("(no structured assessment available)")

        input_text = (
            f"Date: {date_str}\n"
            f"Chief complaint: {session.chief_complaint}\n"
            "Patient reported:\n" + "\n".join(f"- {r}" for r in reported) + "\n"
            "Assessment:\n" + "\n".join(assessment_lines)
        )

        prompt = (
            "Summarize this diagnosis session as concise bullet points from the patient's perspective. "
            "Each bullet should be a single fact. Include: chief complaint with onset/timing/severity "
            "if mentioned, key reported symptoms and relevant negatives the patient confirmed, "
            "and the assessment conclusion. Include the date.\n\n"
            "Do NOT include: recommendations, warnings, advice, medication suggestions, "
            "or anything the AI told the patient. Only include what the patient reported "
            "and what the assessment concluded.\n\n"
            "Format: one fact per line, each starting with '- '. Keep each bullet under 15 words.\n\n"
            f"Session data:\n{input_text}"
        )
        request = LLMRequest(
            task=LLMTask.SUMMARIZATION,
            system_prompt="You summarize medical sessions into concise bullet-point facts.",
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.0,
            max_tokens=4000,
            extra={"reasoning_effort": "low", "think": False},
        )
        response: LLMResponse = await self._agent.call(request)
        narrative = response.content.strip()
        logger.info(
            "Narrative LLM response for session %s: model=%s, len=%d, content=%s",
            session.id,
            response.model,
            len(narrative),
            repr(narrative[:200]) if narrative else "(empty)",
        )
        return narrative

    @staticmethod
    def _build_fallback_narrative(
        session: DiagnosisSession,
        messages: list[dict],
        assessment_tool_args: dict,
    ) -> str:
        """Build bullet-point narrative directly from structured data — no LLM needed."""
        from datetime import date

        lines = [
            f"- Diagnosis session on {date.today().isoformat()} for: {session.chief_complaint}"
        ]

        # Extract user-reported facts from messages
        for m in messages:
            if m["role"] != "user":
                continue
            content = m.get("content", "").strip()
            if not content or content == session.chief_complaint:
                continue
            # Strip enrichment prefix
            if content.startswith("(Q:"):
                paren_end = content.find(")")
                if paren_end != -1:
                    content = content[paren_end + 1 :].strip()
            if content and len(content) < 200:
                lines.append(f"- {content}")

        # Assessment conclusions
        if assessment_tool_args:
            for cond in assessment_tool_args.get("conditions", []):
                name = cond.get("name", "unknown")
                confidence = cond.get("confidence", "")
                lines.append(f"- Assessment: {name} ({confidence})")

        return "\n".join(lines) if len(lines) > 1 else ""

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
                task=LLMTask.TOPIC_GENERATION,
                system_prompt="You generate short topic labels for medical sessions.",
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.3,
                max_tokens=2000,
                extra={"reasoning_effort": "low", "think": False},
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
