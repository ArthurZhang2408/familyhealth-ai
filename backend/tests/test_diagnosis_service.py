"""Comprehensive tests for the diagnosis feature.

Tests cover:
- Session lifecycle (create → message → close)
- Red flag detection and emergency short-circuit
- Safety validation (prohibited patterns)
- LLM integration (mocked)
- Two-pass strategy (Pass 1 conversational + Pass 2 state extraction)
- Memory extraction background task
- Session status enforcement
- API route integration
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.agents.core import AgentCore
from app.agents.registry import ToolRegistry
from app.schemas.diagnosis import (
    DiagnosisPhase,
    Severity,
)
from app.services.diagnosis import DiagnosisService
from app.services.diagnosis_prompts import MEDICAL_DISCLAIMER
from app.services.diagnosis_safety import (
    pre_check_red_flags,
    sanitize_response,
    validate_response,
)

from .conftest import TEST_ACCOUNT_ID

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROFILE_ID = uuid.uuid4()


def _make_profile(**overrides: Any) -> MagicMock:
    """Build a mock Profile with sensible defaults."""
    defaults = {
        "id": PROFILE_ID,
        "account_id": TEST_ACCOUNT_ID,
        "name": "Test Patient",
        "date_of_birth": date(1990, 5, 15),
        "sex": "female",
        "blood_type": "A+",
        "relationship": "self",
        "allergies": [{"allergen": "Penicillin", "severity": "severe", "reaction": "rash"}],
        "current_medications": [
            {"name": "Metformin", "dosage": "500mg", "frequency": "twice daily"}
        ],
        "medical_conditions": [
            {"condition": "Type 2 Diabetes", "diagnosed": "2020", "status": "active"}
        ],
        "family_medical_history": {"Heart Disease": ["Father"]},
        "deleted_at": None,
    }
    defaults.update(overrides)
    profile = MagicMock()
    for k, v in defaults.items():
        setattr(profile, k, v)
    return profile


# Standard mock LLM response for Pass 1 (conversational)
MOCK_LLM_RESPONSE_TEXT = (
    "I understand you're experiencing headaches. Let me ask a few questions "
    "to better understand your symptoms.\n\n"
    "1. When did the headaches start?\n"
    "2. Where exactly do you feel the pain — front, back, or sides of your head?\n"
    "3. How would you describe the pain — is it sharp, dull, throbbing, or pressure-like?"
)

# Standard mock LLM response for Pass 2 (structured state extraction)
MOCK_DIAGNOSIS_STATE = {
    "phase": "characterization",
    "turn_number": 1,
    "severity": "moderate",
    "red_flags_detected": [],
    "information_gathered": {
        "chief_complaint": "recurring headaches",
        "onset": None,
        "location": None,
        "duration": None,
        "character": None,
        "aggravating_factors": None,
        "relieving_factors": None,
        "temporal_pattern": None,
        "severity_rating": None,
        "associated_symptoms": [],
        "self_test_results": [],
        "relevant_risk_factors": ["Type 2 Diabetes", "Family history of Heart Disease"],
    },
    "differential_diagnoses": [],
    "suggested_next_questions": [
        "When did the headaches start?",
        "Where exactly do you feel the pain?",
        "How would you describe the pain?",
    ],
    "ready_for_differential": False,
    "drug_interaction_warnings": [],
}


def _mock_llm_router() -> MagicMock:
    """Create a mock LLMRouter that returns canned responses."""
    router = AsyncMock()

    call_count = {"n": 0}

    async def mock_route(request: Any) -> MagicMock:
        call_count["n"] += 1
        resp = MagicMock()
        # Pass 1 (DIAGNOSIS) returns conversation text
        # Pass 2 (FACT_EXTRACTION) returns JSON state
        if request.task.value == "diagnosis":
            resp.content = MOCK_LLM_RESPONSE_TEXT
        else:
            resp.content = json.dumps(MOCK_DIAGNOSIS_STATE)
        resp.model = "mock-model"
        resp.usage = {"prompt_tokens": 100, "completion_tokens": 50}
        return resp

    router.route = mock_route
    return router


def _mock_context_builder() -> MagicMock:
    """Create a mock ContextBuilder."""
    builder = AsyncMock()
    ctx_result = MagicMock()
    ctx_result.system_prompt = "mock system prompt"
    ctx_result.profile_context = {"name": "Test Patient"}
    ctx_result.memories_used = 0
    ctx_result.token_counts = {"profile": 50, "memories": 0, "total": 100}
    builder.build = AsyncMock(return_value=ctx_result)
    return builder


def _mock_memory_extractor() -> MagicMock:
    """Create a mock MemoryExtractor."""
    extractor = AsyncMock()
    extractor.extract_and_store = AsyncMock(return_value=None)
    return extractor


# ---------------------------------------------------------------------------
# Unit Tests — diagnosis_safety.py
# ---------------------------------------------------------------------------


class TestRedFlagPreCheck:
    def test_no_flags_normal_message(self) -> None:
        flags = pre_check_red_flags("I have a mild headache")
        assert flags == []

    def test_cardiovascular_flag(self) -> None:
        flags = pre_check_red_flags("I'm having severe chest pain")
        assert len(flags) == 1
        assert "cardiovascular" in flags[0]

    def test_neurological_flag(self) -> None:
        flags = pre_check_red_flags("I have the worst headache of my life")
        assert len(flags) == 1
        assert "neurological" in flags[0]

    def test_psychiatric_flag(self) -> None:
        flags = pre_check_red_flags("I want to kill myself")
        assert len(flags) == 1
        assert "psychiatric" in flags[0]

    def test_anaphylaxis_flag(self) -> None:
        flags = pre_check_red_flags("My throat closing and I can't swallow")
        assert len(flags) == 1
        assert "anaphylaxis" in flags[0]

    def test_respiratory_flag(self) -> None:
        flags = pre_check_red_flags("I'm coughing blood")
        assert len(flags) == 1
        assert "respiratory" in flags[0]

    def test_multiple_flags(self) -> None:
        flags = pre_check_red_flags("I have chest pain and face drooping and slurred speech")
        assert len(flags) >= 2

    def test_case_insensitive(self) -> None:
        flags = pre_check_red_flags("I'm having CHEST PAIN")
        assert len(flags) == 1

    def test_pediatric_fever_flag(self) -> None:
        flags = pre_check_red_flags("baby has a fever", profile_age=0.1)
        assert len(flags) == 1
        assert "pediatric" in flags[0]

    def test_abdominal_flag(self) -> None:
        flags = pre_check_red_flags("I've been vomiting blood")
        assert len(flags) == 1
        assert "abdominal" in flags[0]

    def test_trauma_flag(self) -> None:
        flags = pre_check_red_flags("I hit my head and feel confused")
        assert len(flags) >= 1
        assert any("trauma" in f for f in flags)

    def test_pediatric_no_flag_older_child(self) -> None:
        flags = pre_check_red_flags("child has a fever", profile_age=5.0)
        assert flags == []


class TestResponseValidation:
    def test_clean_response(self) -> None:
        text = "Based on your symptoms, this could indicate a tension headache."
        assert validate_response(text) == []

    def test_dosage_recommendation(self) -> None:
        text = "I recommend you take 500 mg of ibuprofen."
        violations = validate_response(text)
        assert len(violations) > 0

    def test_cancer_diagnosis(self) -> None:
        text = "You have cancer and should seek treatment."
        violations = validate_response(text)
        assert len(violations) > 0

    def test_no_doctor_needed(self) -> None:
        text = "You don't need to see a doctor for this."
        violations = validate_response(text)
        assert len(violations) > 0

    def test_prognosis(self) -> None:
        text = "The survival rate for this condition is low."
        violations = validate_response(text)
        assert len(violations) > 0


class TestSanitizeResponse:
    def test_no_violations(self) -> None:
        text = "This looks like a cold."
        assert sanitize_response(text, []) == text

    def test_with_violations(self) -> None:
        text = "Take 500 mg of aspirin."
        result = sanitize_response(text, ["dosage violation"])
        assert "healthcare professional" in result
        assert text in result


# ---------------------------------------------------------------------------
# Unit Tests — DiagnosisService
# ---------------------------------------------------------------------------


class TestDiagnosisServiceCreateSession:
    @pytest.mark.asyncio
    async def test_create_session_normal(self, db_session: Any) -> None:
        """Normal session creation: LLM is called, messages stored."""
        profile = _make_profile()
        svc = DiagnosisService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        # Need a real profile in DB for context builder / message storage
        from app.models.profile import Profile as ProfileModel

        real_profile = ProfileModel(
            id=profile.id,
            account_id=profile.account_id,
            name=profile.name,
            relationship=profile.relationship,
        )
        db_session.add(real_profile)
        await db_session.flush()

        session, turn = await svc.create_session(profile, "recurring headaches")
        await db_session.commit()

        assert session.status == "active"
        assert session.chief_complaint == "recurring headaches"
        assert turn.disclaimer == MEDICAL_DISCLAIMER
        assert turn.message.role == "assistant"
        assert turn.message.content == MOCK_LLM_RESPONSE_TEXT
        assert turn.diagnosis_state.phase == DiagnosisPhase.CHARACTERIZATION

    @pytest.mark.asyncio
    async def test_create_session_red_flag(self, db_session: Any) -> None:
        """Red flag in chief complaint: emergency template used, LLM NOT called."""
        profile = _make_profile()
        svc = DiagnosisService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        from app.models.profile import Profile as ProfileModel

        real_profile = ProfileModel(
            id=profile.id,
            account_id=profile.account_id,
            name=profile.name,
            relationship=profile.relationship,
        )
        db_session.add(real_profile)
        await db_session.flush()

        session, turn = await svc.create_session(profile, "I'm having severe chest pain")
        await db_session.commit()

        assert turn.diagnosis_state.severity == Severity.EMERGENCY
        assert len(turn.diagnosis_state.red_flags_detected) > 0
        assert "emergency" in turn.message.content.lower() or "911" in turn.message.content


class TestDiagnosisServiceSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_normal(self, db_session: Any) -> None:
        """Normal message flow: LLM called, messages stored."""
        profile = _make_profile()
        svc = DiagnosisService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        from app.models.profile import Profile as ProfileModel

        real_profile = ProfileModel(
            id=profile.id,
            account_id=profile.account_id,
            name=profile.name,
            relationship=profile.relationship,
        )
        db_session.add(real_profile)
        await db_session.flush()

        session, _ = await svc.create_session(profile, "recurring headaches")

        turn = await svc.send_message(
            session, profile, "The headaches started about two weeks ago"
        )
        await db_session.commit()

        assert turn.message.role == "assistant"
        assert turn.disclaimer == MEDICAL_DISCLAIMER

    @pytest.mark.asyncio
    async def test_send_message_to_resolved_session(self, db_session: Any) -> None:
        """Cannot send messages to a resolved session."""
        profile = _make_profile()
        svc = DiagnosisService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        from app.models.profile import Profile as ProfileModel

        real_profile = ProfileModel(
            id=profile.id,
            account_id=profile.account_id,
            name=profile.name,
            relationship=profile.relationship,
        )
        db_session.add(real_profile)
        await db_session.flush()

        session, _ = await svc.create_session(profile, "mild cough")
        await svc.close_session(session, profile, "Got better")

        from app.core.exceptions import AppError

        with pytest.raises(AppError) as exc_info:
            await svc.send_message(session, profile, "Another question")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_send_message_red_flag(self, db_session: Any) -> None:
        """Red flag in follow-up message triggers emergency response."""
        profile = _make_profile()
        svc = DiagnosisService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        from app.models.profile import Profile as ProfileModel

        real_profile = ProfileModel(
            id=profile.id,
            account_id=profile.account_id,
            name=profile.name,
            relationship=profile.relationship,
        )
        db_session.add(real_profile)
        await db_session.flush()

        session, _ = await svc.create_session(profile, "feeling dizzy")
        turn = await svc.send_message(
            session, profile, "now I also have chest pain and can't breathe"
        )
        await db_session.commit()

        assert turn.diagnosis_state.severity == Severity.EMERGENCY


class TestDiagnosisServiceCloseSession:
    @pytest.mark.asyncio
    async def test_close_session(self, db_session: Any) -> None:
        """Close session stores resolution notes and triggers memory extraction."""
        profile = _make_profile()
        extractor = _mock_memory_extractor()
        svc = DiagnosisService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=extractor,
        )

        from app.models.profile import Profile as ProfileModel

        real_profile = ProfileModel(
            id=profile.id,
            account_id=profile.account_id,
            name=profile.name,
            relationship=profile.relationship,
        )
        db_session.add(real_profile)
        await db_session.flush()

        session, _ = await svc.create_session(profile, "sore throat")
        result = await svc.close_session(session, profile, "Doctor confirmed strep throat")
        await db_session.commit()

        assert result.status == "resolved"
        assert result.resolution_notes == "Doctor confirmed strep throat"
        # Memory extraction was called
        extractor.extract_and_store.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_already_resolved(self, db_session: Any) -> None:
        """Cannot close an already-resolved session."""
        profile = _make_profile()
        svc = DiagnosisService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        from app.models.profile import Profile as ProfileModel

        real_profile = ProfileModel(
            id=profile.id,
            account_id=profile.account_id,
            name=profile.name,
            relationship=profile.relationship,
        )
        db_session.add(real_profile)
        await db_session.flush()

        session, _ = await svc.create_session(profile, "mild cough")
        await svc.close_session(session, profile)

        from app.core.exceptions import AppError

        with pytest.raises(AppError):
            await svc.close_session(session, profile, "again")


class TestDiagnosisServiceStateExtraction:
    @pytest.mark.asyncio
    async def test_state_extraction_fallback(self, db_session: Any) -> None:
        """Pass 2 failure results in fallback state, not an error."""
        profile = _make_profile()

        # LLM that fails on Pass 2
        llm = AsyncMock()
        call_count = {"n": 0}

        async def failing_pass2(request: Any) -> MagicMock:
            call_count["n"] += 1
            resp = MagicMock()
            if request.task.value == "diagnosis":
                resp.content = "Here is my response about your symptoms."
            else:
                raise RuntimeError("Pass 2 LLM failure")
            return resp

        llm.route = failing_pass2

        svc = DiagnosisService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=llm,
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        from app.models.profile import Profile as ProfileModel

        real_profile = ProfileModel(
            id=profile.id,
            account_id=profile.account_id,
            name=profile.name,
            relationship=profile.relationship,
        )
        db_session.add(real_profile)
        await db_session.flush()

        session, turn = await svc.create_session(profile, "mild headache")
        await db_session.commit()

        # Response still delivered, fallback state used
        assert turn.message.content == "Here is my response about your symptoms."
        assert turn.diagnosis_state.phase == DiagnosisPhase.UNKNOWN
        assert turn.diagnosis_state.severity == Severity.MODERATE


class TestDiagnosisServiceListSessions:
    @pytest.mark.asyncio
    async def test_list_sessions(self, db_session: Any) -> None:
        profile = _make_profile()
        svc = DiagnosisService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        from app.models.profile import Profile as ProfileModel

        real_profile = ProfileModel(
            id=profile.id,
            account_id=profile.account_id,
            name=profile.name,
            relationship=profile.relationship,
        )
        db_session.add(real_profile)
        await db_session.flush()

        await svc.create_session(profile, "headache")
        await svc.create_session(profile, "sore throat")
        await db_session.commit()

        result = await svc.list_sessions(profile.id)
        assert result.total == 2
        assert len(result.items) == 2

    @pytest.mark.asyncio
    async def test_list_sessions_with_status_filter(self, db_session: Any) -> None:
        profile = _make_profile()
        svc = DiagnosisService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        from app.models.profile import Profile as ProfileModel

        real_profile = ProfileModel(
            id=profile.id,
            account_id=profile.account_id,
            name=profile.name,
            relationship=profile.relationship,
        )
        db_session.add(real_profile)
        await db_session.flush()

        session1, _ = await svc.create_session(profile, "headache")
        session2, _ = await svc.create_session(profile, "sore throat")
        await svc.close_session(session1, profile)
        await db_session.commit()

        active = await svc.list_sessions(profile.id, status="active")
        assert active.total == 1

        resolved = await svc.list_sessions(profile.id, status="resolved")
        assert resolved.total == 1


class TestMemoryExtraction:
    @pytest.mark.asyncio
    async def test_extractor_called_with_correct_args(self) -> None:
        """Verify MemoryExtractor.extract_and_store is callable with diagnosis args."""
        extractor = _mock_memory_extractor()
        profile_id = uuid.uuid4()
        session_id = uuid.uuid4()

        await extractor.extract_and_store(
            profile_id=profile_id,
            messages=[
                {"role": "user", "content": "I have headaches"},
                {"role": "assistant", "content": "Let me ask some questions..."},
            ],
            source=f"diagnosis:{session_id}",
            category="diagnoses",
        )

        extractor.extract_and_store.assert_called_once()
        call_kwargs = extractor.extract_and_store.call_args
        assert call_kwargs.kwargs["profile_id"] == profile_id
        assert call_kwargs.kwargs["source"] == f"diagnosis:{session_id}"
        assert call_kwargs.kwargs["category"] == "diagnoses"


# ---------------------------------------------------------------------------
# Integration Tests — API routes
# ---------------------------------------------------------------------------


@pytest.fixture
def _override_diagnosis_deps(client: AsyncClient, db_session: Any) -> Iterator[None]:
    """Override agent/memory deps for route-level tests."""
    from app.agents.core import AgentCore
    from app.agents.registry import ToolRegistry
    from app.api.deps import get_agent_core, get_context_builder, get_memory_extractor
    from app.main import app

    # Build an AgentCore that wraps the mock LLM router
    mock_router = _mock_llm_router()
    mock_agent_core = AgentCore(llm_router=mock_router, tool_registry=ToolRegistry())

    app.dependency_overrides[get_agent_core] = lambda: mock_agent_core
    app.dependency_overrides[get_context_builder] = _mock_context_builder
    app.dependency_overrides[get_memory_extractor] = _mock_memory_extractor

    yield

    app.dependency_overrides.pop(get_agent_core, None)
    app.dependency_overrides.pop(get_context_builder, None)
    app.dependency_overrides.pop(get_memory_extractor, None)


async def _create_profile(client: AsyncClient) -> uuid.UUID:
    """Helper to create a profile via API."""
    resp = await client.post(
        "/api/v1/profiles",
        json={
            "name": "Test Patient",
            "relationship": "self",
        },
    )
    assert resp.status_code == 201
    return uuid.UUID(resp.json()["id"])


class TestDiagnosisRoutes:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_create_session_route(self, client: AsyncClient) -> None:
        pid = await _create_profile(client)
        resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "recurring headaches"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "message" in data
        assert "diagnosis_state" in data
        assert "disclaimer" in data
        assert data["message"]["role"] == "assistant"
        assert data["disclaimer"] == MEDICAL_DISCLAIMER

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_send_message_route(self, client: AsyncClient) -> None:
        pid = await _create_profile(client)
        # Create session
        create_resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "mild cough"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["message"]["session_id"]

        # Send message
        msg_resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis/{session_id}/messages",
            data={"content": "The cough started 3 days ago"},
        )
        assert msg_resp.status_code == 201
        data = msg_resp.json()
        assert data["message"]["role"] == "assistant"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_list_sessions_route(self, client: AsyncClient) -> None:
        pid = await _create_profile(client)
        await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "headache"},
        )
        await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "sore throat"},
        )

        resp = await client.get(f"/api/v1/profiles/{pid}/diagnosis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_get_session_route(self, client: AsyncClient) -> None:
        pid = await _create_profile(client)
        create_resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "back pain"},
        )
        session_id = create_resp.json()["message"]["session_id"]

        resp = await client.get(f"/api/v1/profiles/{pid}/diagnosis/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chief_complaint"] == "back pain"
        assert len(data["messages"]) == 2  # user + assistant

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_close_session_route(self, client: AsyncClient) -> None:
        pid = await _create_profile(client)
        create_resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "stomach ache"},
        )
        session_id = create_resp.json()["message"]["session_id"]

        resp = await client.patch(
            f"/api/v1/profiles/{pid}/diagnosis/{session_id}",
            json={"status": "resolved", "resolution_notes": "Was indigestion"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "resolved"
        assert data["resolution_notes"] == "Was indigestion"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_send_message_to_closed_session(self, client: AsyncClient) -> None:
        pid = await _create_profile(client)
        create_resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "knee pain"},
        )
        session_id = create_resp.json()["message"]["session_id"]

        # Close session
        await client.patch(
            f"/api/v1/profiles/{pid}/diagnosis/{session_id}",
            json={"status": "resolved"},
        )

        # Try to send message
        resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis/{session_id}/messages",
            data={"content": "Follow-up question"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_red_flag_route(self, client: AsyncClient) -> None:
        pid = await _create_profile(client)
        resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "I'm having severe chest pain and can't breathe"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["diagnosis_state"]["severity"] == "emergency"
        assert len(data["diagnosis_state"]["red_flags_detected"]) > 0

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_nonexistent_session(self, client: AsyncClient) -> None:
        pid = await _create_profile(client)
        fake_sid = uuid.uuid4()
        resp = await client.get(f"/api/v1/profiles/{pid}/diagnosis/{fake_sid}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_abandon_session_route(self, client: AsyncClient) -> None:
        pid = await _create_profile(client)
        create_resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "rash on arm"},
        )
        session_id = create_resp.json()["message"]["session_id"]

        resp = await client.patch(
            f"/api/v1/profiles/{pid}/diagnosis/{session_id}",
            json={"status": "abandoned"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "abandoned"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_status_filter_route(self, client: AsyncClient) -> None:
        pid = await _create_profile(client)
        # Create two sessions
        resp1 = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "headache"},
        )
        await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "cough"},
        )
        # Close one
        sid1 = resp1.json()["message"]["session_id"]
        await client.patch(
            f"/api/v1/profiles/{pid}/diagnosis/{sid1}",
            json={"status": "resolved"},
        )

        # Filter by active
        resp = await client.get(f"/api/v1/profiles/{pid}/diagnosis?status=active")
        assert resp.json()["total"] == 1

        # Filter by resolved
        resp = await client.get(f"/api/v1/profiles/{pid}/diagnosis?status=resolved")
        assert resp.json()["total"] == 1


# ---------------------------------------------------------------------------
# Full session lifecycle test
# ---------------------------------------------------------------------------


class TestFullSessionLifecycle:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_full_flow(self, client: AsyncClient) -> None:
        """Test: create session → send messages → close session."""
        pid = await _create_profile(client)

        # 1. Create session
        resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "recurring headaches for 2 weeks"},
        )
        assert resp.status_code == 201
        session_id = resp.json()["message"]["session_id"]
        assert resp.json()["diagnosis_state"]["phase"] is not None

        # 2. Send follow-up messages
        for msg in [
            "They started about 2 weeks ago, mostly in the morning",
            "The pain is dull and throbbing, usually at the front of my head",
            "Stress and screen time seem to make it worse",
        ]:
            resp = await client.post(
                f"/api/v1/profiles/{pid}/diagnosis/{session_id}/messages",
                data={"content": msg},
            )
            assert resp.status_code == 201
            assert resp.json()["message"]["role"] == "assistant"

        # 3. Get session — verify all messages stored
        resp = await client.get(f"/api/v1/profiles/{pid}/diagnosis/{session_id}")
        assert resp.status_code == 200
        messages = resp.json()["messages"]
        # 1 initial (user+assistant) + 3 follow-ups (user+assistant each) = 8 messages
        assert len(messages) == 8

        # 4. Close session
        resp = await client.patch(
            f"/api/v1/profiles/{pid}/diagnosis/{session_id}",
            json={
                "status": "resolved",
                "resolution_notes": "Tension headaches. Doctor prescribed rest.",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"


class TestDeleteSession:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_delete_session(self, client: AsyncClient) -> None:
        from app.api.deps import get_memory_service
        from app.main import app

        mock_mem_svc = MagicMock()
        mock_mem_svc.delete_by_source = AsyncMock(return_value=1)
        app.dependency_overrides[get_memory_service] = lambda: mock_mem_svc

        pid = await _create_profile(client)

        # Create a session
        resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "test headache"},
        )
        assert resp.status_code == 201
        session_id = resp.json()["message"]["session_id"]

        # Delete it
        resp2 = await client.delete(f"/api/v1/profiles/{pid}/diagnosis/{session_id}")
        assert resp2.status_code == 204

        # Verify it's gone
        resp3 = await client.get(f"/api/v1/profiles/{pid}/diagnosis/{session_id}")
        assert resp3.status_code == 404

        # Verify memory service was called
        mock_mem_svc.delete_by_source.assert_called_once_with(
            uuid.UUID(str(pid)), f"diagnosis:{session_id}"
        )

        app.dependency_overrides.pop(get_memory_service, None)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_delete_session_not_found(self, client: AsyncClient) -> None:
        from app.api.deps import get_memory_service
        from app.main import app

        mock_mem_svc = MagicMock()
        mock_mem_svc.delete_by_source = AsyncMock(return_value=0)
        app.dependency_overrides[get_memory_service] = lambda: mock_mem_svc

        pid = await _create_profile(client)
        resp = await client.delete(f"/api/v1/profiles/{pid}/diagnosis/{uuid.uuid4()}")
        assert resp.status_code == 404

        app.dependency_overrides.pop(get_memory_service, None)


class TestRenameSession:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_rename_session(self, client: AsyncClient) -> None:
        pid = await _create_profile(client)

        # Create a session
        resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "test headache"},
        )
        assert resp.status_code == 201
        session_id = resp.json()["message"]["session_id"]

        # Rename it
        resp2 = await client.patch(
            f"/api/v1/profiles/{pid}/diagnosis/{session_id}/rename",
            json={"title": "Recurring migraine"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["title"] == "Recurring migraine"
        # chief_complaint should be unchanged
        assert resp2.json()["chief_complaint"] == "test headache"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_rename_session_not_found(self, client: AsyncClient) -> None:
        pid = await _create_profile(client)
        resp = await client.patch(
            f"/api/v1/profiles/{pid}/diagnosis/{uuid.uuid4()}/rename",
            json={"title": "Something"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_override_diagnosis_deps")
    async def test_rename_session_empty_title(self, client: AsyncClient) -> None:
        pid = await _create_profile(client)

        resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "test headache"},
        )
        assert resp.status_code == 201
        session_id = resp.json()["message"]["session_id"]

        # Empty title should fail validation
        resp2 = await client.patch(
            f"/api/v1/profiles/{pid}/diagnosis/{session_id}/rename",
            json={"title": ""},
        )
        assert resp2.status_code == 422
