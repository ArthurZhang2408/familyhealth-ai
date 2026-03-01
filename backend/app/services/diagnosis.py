"""DiagnosisService — orchestrates the diagnosis agent feature."""

from __future__ import annotations

import copy
import json
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.core import AgentCore
from app.agents.definitions import DIAGNOSIS_AGENT
from app.agents.session import AgentSession
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

        # Store messages
        user_msg = DiagnosisMessage(session_id=session.id, role="user", content=chief_complaint)
        assistant_msg = DiagnosisMessage(
            session_id=session.id, role="assistant", content=conversation_text
        )
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

        await self._db.flush()
        await self._db.refresh(user_msg)
        await self._db.refresh(assistant_msg)

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

        # Store messages
        user_msg = DiagnosisMessage(session_id=session.id, role="user", content=content)
        assistant_msg = DiagnosisMessage(
            session_id=session.id, role="assistant", content=conversation_text
        )
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

        await self._db.flush()
        await self._db.refresh(user_msg)
        await self._db.refresh(assistant_msg)

        return DiagnosisTurnResponse(
            message=DiagnosisMessageResponse.model_validate(assistant_msg),
            diagnosis_state=diagnosis_state,
            disclaimer=MEDICAL_DISCLAIMER,
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

        # Extract resolution facts to long-term memory (best-effort)
        try:
            await self._mem_extractor.extract_and_store(
                profile_id=profile.id,
                messages=[{"role": "system", "content": resolution_summary}],
                source=f"diagnosis:{session.id}:resolution",
                category="diagnoses",
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

        messages = [{"role": m.role, "content": m.content} for m in history]

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
