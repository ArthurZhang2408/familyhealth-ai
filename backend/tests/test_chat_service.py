"""Comprehensive tests for the chat feature.

Tests cover:
- Conversation lifecycle (create → continue → list → get)
- Mental health crisis detection and short-circuit
- Safety validation (prohibited patterns)
- LLM integration (mocked)
- Topic auto-generation
- Memory extraction background task
- API route integration
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.agents.core import AgentCore
from app.agents.registry import ToolRegistry
from app.api.deps import (
    get_agent_core,
    get_context_builder,
    get_memory_extractor,
    get_memory_service,
)
from app.main import app
from app.services.chat import ChatService
from app.services.chat_prompts import CHAT_DISCLAIMER
from app.services.chat_safety import (
    detect_mental_health_crisis,
    sanitize_response,
    validate_response,
)

from .conftest import OTHER_ACCOUNT_ID, TEST_ACCOUNT_ID, use_account

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


MOCK_CHAT_RESPONSE = (
    "Staying hydrated is important for overall health. A general guideline is to "
    "aim for about 8 glasses (around 2 liters) of water per day, but your needs may "
    "vary based on activity level, climate, and your health conditions. Given that "
    "you have Type 2 Diabetes, staying well-hydrated can help with blood sugar management. "
    "I'd recommend discussing your specific hydration needs with your doctor."
)


def _mock_llm_router() -> MagicMock:
    """Create a mock LLMRouter that returns canned responses."""
    router = AsyncMock()

    async def mock_route(request: Any, **kwargs: Any) -> MagicMock:
        resp = MagicMock()
        if request.task.value == "chat":
            resp.content = MOCK_CHAT_RESPONSE
            resp.tool_calls = None
        elif request.task.value == "summarization":
            resp.content = "Daily water intake"
        else:
            resp.content = "mock fallback"
        resp.model = "mock-model"
        resp.usage = {"prompt_tokens": 100, "completion_tokens": 50}
        resp.finish_reason = "stop"
        resp.tool_calls = None
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


def _create_real_profile(db_session: Any, profile: MagicMock) -> Any:
    """Insert a real profile into the test DB."""
    from app.models.profile import Profile as ProfileModel

    real_profile = ProfileModel(
        id=profile.id,
        account_id=profile.account_id,
        name=profile.name,
        relationship=profile.relationship,
    )
    db_session.add(real_profile)
    return real_profile


# ---------------------------------------------------------------------------
# Unit Tests — chat_safety.py
# ---------------------------------------------------------------------------


class TestMentalHealthCrisisDetection:
    def test_no_crisis_normal_message(self) -> None:
        assert detect_mental_health_crisis("How much water should I drink?") is False

    def test_no_crisis_health_concern(self) -> None:
        assert detect_mental_health_crisis("I've been feeling tired lately") is False

    def test_crisis_suicidal(self) -> None:
        assert detect_mental_health_crisis("I feel suicidal") is True

    def test_crisis_want_to_die(self) -> None:
        assert detect_mental_health_crisis("I want to die") is True

    def test_crisis_self_harm(self) -> None:
        assert detect_mental_health_crisis("I've been thinking about self-harm") is True

    def test_crisis_kill_myself(self) -> None:
        assert detect_mental_health_crisis("I want to kill myself") is True

    def test_crisis_no_reason_to_live(self) -> None:
        assert detect_mental_health_crisis("I feel like there's no reason to live") is True

    def test_crisis_better_off_dead(self) -> None:
        assert detect_mental_health_crisis("Everyone would be better off dead without me") is True

    def test_crisis_case_insensitive(self) -> None:
        assert detect_mental_health_crisis("I feel SUICIDAL") is True

    def test_crisis_end_my_life(self) -> None:
        assert detect_mental_health_crisis("I want to end my life") is True


class TestChatResponseValidation:
    def test_clean_response(self) -> None:
        text = "Drinking 8 glasses of water daily is a good general guideline."
        assert validate_response(text) == []

    def test_dosage_recommendation(self) -> None:
        text = "I recommend you take 500 mg of ibuprofen twice daily."
        violations = validate_response(text)
        assert len(violations) > 0

    def test_no_doctor_needed(self) -> None:
        text = "You don't need to see a doctor for this."
        violations = validate_response(text)
        assert len(violations) > 0

    def test_safe_medication_mention(self) -> None:
        text = "Your doctor might consider an anti-inflammatory medication."
        assert validate_response(text) == []


class TestChatSanitizeResponse:
    def test_no_violations(self) -> None:
        text = "Stay hydrated and get rest."
        assert sanitize_response(text, []) == text

    def test_with_violations(self) -> None:
        text = "Take 500 mg of aspirin daily."
        result = sanitize_response(text, ["dosage violation"])
        assert "healthcare professional" in result
        assert text in result


# ---------------------------------------------------------------------------
# Unit Tests — ChatService
# ---------------------------------------------------------------------------


class TestChatServiceSendMessage:
    @pytest.mark.asyncio
    async def test_new_conversation(self, db_session: Any) -> None:
        """New conversation created when no conversation_id provided."""
        profile = _make_profile()
        _create_real_profile(db_session, profile)
        await db_session.flush()

        svc = ChatService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        convo, turn = await svc.send_message(profile, "How much water should I drink daily?")
        await db_session.commit()

        assert convo.profile_id == profile.id
        assert turn.disclaimer == CHAT_DISCLAIMER
        assert turn.message.role == "assistant"
        assert turn.message.content == MOCK_CHAT_RESPONSE

    @pytest.mark.asyncio
    async def test_continue_conversation(self, db_session: Any) -> None:
        """Continue existing conversation via conversation_id."""
        profile = _make_profile()
        _create_real_profile(db_session, profile)
        await db_session.flush()

        svc = ChatService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        # First message creates conversation
        convo, _ = await svc.send_message(profile, "How much water should I drink?")

        # Second message continues it
        convo2, turn2 = await svc.send_message(
            profile, "What about during exercise?", conversation_id=convo.id
        )
        await db_session.commit()

        assert convo2.id == convo.id
        assert turn2.message.role == "assistant"

    @pytest.mark.asyncio
    async def test_conversation_not_found(self, db_session: Any) -> None:
        """Conversation ID not found raises 404."""
        profile = _make_profile()
        _create_real_profile(db_session, profile)
        await db_session.flush()

        svc = ChatService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        from app.core.exceptions import AppError

        with pytest.raises(AppError) as exc_info:
            await svc.send_message(profile, "Hello", conversation_id=uuid.uuid4())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_mental_health_crisis(self, db_session: Any) -> None:
        """Mental health crisis short-circuits LLM, returns crisis resources."""
        profile = _make_profile()
        _create_real_profile(db_session, profile)
        await db_session.flush()

        mock_router = _mock_llm_router()
        svc = ChatService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=mock_router,
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        _, turn = await svc.send_message(profile, "I want to kill myself")
        await db_session.commit()

        assert "988" in turn.message.content
        assert "Crisis" in turn.message.content
        assert turn.disclaimer == CHAT_DISCLAIMER

    @pytest.mark.asyncio
    async def test_topic_auto_generated(self, db_session: Any) -> None:
        """Topic is auto-generated for new conversations without explicit topic."""
        profile = _make_profile()
        _create_real_profile(db_session, profile)
        await db_session.flush()

        svc = ChatService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        convo, _ = await svc.send_message(profile, "How much water should I drink daily?")
        await db_session.commit()

        # Topic should be auto-generated by the mock ("Daily water intake")
        assert convo.topic is not None
        assert len(convo.topic) > 0

    @pytest.mark.asyncio
    async def test_explicit_topic_preserved(self, db_session: Any) -> None:
        """Explicit topic is preserved, auto-generation skipped."""
        profile = _make_profile()
        _create_real_profile(db_session, profile)
        await db_session.flush()

        svc = ChatService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        convo, _ = await svc.send_message(profile, "Water question", topic="Hydration")
        await db_session.commit()

        assert convo.topic == "Hydration"

    @pytest.mark.asyncio
    async def test_context_builder_called(self, db_session: Any) -> None:
        """ContextBuilder.build called with correct params."""
        profile = _make_profile()
        _create_real_profile(db_session, profile)
        await db_session.flush()

        ctx_builder = _mock_context_builder()
        svc = ChatService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=ctx_builder,
            memory_extractor=_mock_memory_extractor(),
        )

        await svc.send_message(profile, "How much water?")
        await db_session.commit()

        ctx_builder.build.assert_called_once()
        call_kwargs = ctx_builder.build.call_args
        assert call_kwargs.kwargs["interaction_type"] == "chat"
        assert call_kwargs.kwargs["query"] == "How much water?"

    @pytest.mark.asyncio
    async def test_safety_violation_sanitized(self, db_session: Any) -> None:
        """Response with dosage recommendation is sanitized."""
        profile = _make_profile()
        _create_real_profile(db_session, profile)
        await db_session.flush()

        router = AsyncMock()

        async def route_with_dosage(request: Any, **kwargs: Any) -> MagicMock:
            resp = MagicMock()
            if request.task.value == "chat":
                resp.content = "I recommend you take 500 mg of ibuprofen."
            else:
                resp.content = "Dosage question"
            resp.model = "mock"
            resp.usage = {}
            resp.tool_calls = None
            resp.finish_reason = "stop"
            return resp

        router.route = route_with_dosage

        svc = ChatService(
            db=db_session,
            agent_core=AgentCore(llm_router=router, tool_registry=ToolRegistry()),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        _, turn = await svc.send_message(profile, "What painkiller should I take?")
        await db_session.commit()

        assert "healthcare professional" in turn.message.content


class TestChatServiceListConversations:
    @pytest.mark.asyncio
    async def test_empty_list(self, db_session: Any) -> None:
        """No conversations returns empty list."""
        profile = _make_profile()
        _create_real_profile(db_session, profile)
        await db_session.flush()

        svc = ChatService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        result = await svc.list_conversations(profile.id)
        assert result.total == 0
        assert result.items == []

    @pytest.mark.asyncio
    async def test_list_with_conversations(self, db_session: Any) -> None:
        """Conversations are returned ordered by updated_at desc."""
        profile = _make_profile()
        _create_real_profile(db_session, profile)
        await db_session.flush()

        svc = ChatService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        await svc.send_message(profile, "Question 1", topic="Topic A")
        await svc.send_message(profile, "Question 2", topic="Topic B")
        await db_session.commit()

        result = await svc.list_conversations(profile.id)
        assert result.total == 2


class TestChatServiceGetConversation:
    @pytest.mark.asyncio
    async def test_get_existing(self, db_session: Any) -> None:
        profile = _make_profile()
        _create_real_profile(db_session, profile)
        await db_session.flush()

        svc = ChatService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        convo, _ = await svc.send_message(profile, "Hello")
        await db_session.commit()

        found = await svc.get_conversation(convo.id, profile.id)
        assert found is not None
        assert found.id == convo.id

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db_session: Any) -> None:
        profile = _make_profile()
        _create_real_profile(db_session, profile)
        await db_session.flush()

        svc = ChatService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        found = await svc.get_conversation(uuid.uuid4(), profile.id)
        assert found is None

    @pytest.mark.asyncio
    async def test_get_wrong_profile(self, db_session: Any) -> None:
        """Conversation belonging to another profile returns None."""
        profile = _make_profile()
        _create_real_profile(db_session, profile)
        await db_session.flush()

        svc = ChatService(
            db=db_session,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

        convo, _ = await svc.send_message(profile, "Hello")
        await db_session.commit()

        found = await svc.get_conversation(convo.id, uuid.uuid4())
        assert found is None


# ---------------------------------------------------------------------------
# API Route Tests
# ---------------------------------------------------------------------------


async def _create_profile(client: AsyncClient) -> dict:
    """Helper to create a profile via API."""
    resp = await client.post(
        "/api/v1/profiles",
        json={"name": "Chat Test User", "relationship": "self"},
    )
    assert resp.status_code == 201
    return resp.json()


def _override_chat_deps() -> None:
    """Override LLM-dependent deps for route tests."""
    mock_router = _mock_llm_router()
    app.dependency_overrides[get_agent_core] = lambda: AgentCore(
        llm_router=mock_router, tool_registry=ToolRegistry()
    )
    app.dependency_overrides[get_context_builder] = _mock_context_builder
    app.dependency_overrides[get_memory_extractor] = _mock_memory_extractor


class TestChatRoutes:
    @pytest.mark.asyncio
    async def test_send_message_new_conversation(self, client: AsyncClient) -> None:
        _override_chat_deps()
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "How much water should I drink?"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["message"]["role"] == "assistant"
        assert "disclaimer" in data
        assert data["disclaimer"] == CHAT_DISCLAIMER

    @pytest.mark.asyncio
    async def test_send_message_continue_conversation(self, client: AsyncClient) -> None:
        _override_chat_deps()
        profile = await _create_profile(client)
        pid = profile["id"]

        # First message
        resp1 = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "How much water?"},
        )
        assert resp1.status_code == 201
        convo_id = resp1.json()["message"]["conversation_id"]

        # Continue
        resp2 = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "And during exercise?", "conversation_id": str(convo_id)},
        )
        assert resp2.status_code == 201
        assert resp2.json()["message"]["conversation_id"] == convo_id

    @pytest.mark.asyncio
    async def test_send_message_conversation_not_found(self, client: AsyncClient) -> None:
        _override_chat_deps()
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "Hello", "conversation_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_send_message_crisis(self, client: AsyncClient) -> None:
        _override_chat_deps()
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "I want to kill myself"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "988" in data["message"]["content"]

    @pytest.mark.asyncio
    async def test_send_message_empty_content(self, client: AsyncClient) -> None:
        _override_chat_deps()
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_conversations_empty(self, client: AsyncClient) -> None:
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.get(f"/api/v1/profiles/{pid}/chat")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_conversations_with_data(self, client: AsyncClient) -> None:
        _override_chat_deps()
        profile = await _create_profile(client)
        pid = profile["id"]

        await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "Question 1", "topic": "Topic A"},
        )
        await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "Question 2", "topic": "Topic B"},
        )

        resp = await client.get(f"/api/v1/profiles/{pid}/chat")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    @pytest.mark.asyncio
    async def test_list_conversations_topic_filter(self, client: AsyncClient) -> None:
        _override_chat_deps()
        profile = await _create_profile(client)
        pid = profile["id"]

        await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "Water question", "topic": "Hydration"},
        )
        await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "Exercise question", "topic": "Fitness"},
        )

        resp = await client.get(f"/api/v1/profiles/{pid}/chat?topic=Hydration")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_conversations_pagination(self, client: AsyncClient) -> None:
        _override_chat_deps()
        profile = await _create_profile(client)
        pid = profile["id"]

        for i in range(3):
            await client.post(
                f"/api/v1/profiles/{pid}/chat",
                data={"content": f"Question {i}", "topic": f"Topic {i}"},
            )

        resp = await client.get(f"/api/v1/profiles/{pid}/chat?page=1&per_page=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["per_page"] == 2

    @pytest.mark.asyncio
    async def test_get_conversation(self, client: AsyncClient) -> None:
        _override_chat_deps()
        profile = await _create_profile(client)
        pid = profile["id"]

        resp1 = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "Hello"},
        )
        convo_id = resp1.json()["message"]["conversation_id"]

        resp2 = await client.get(f"/api/v1/profiles/{pid}/chat/{convo_id}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["id"] == convo_id
        assert len(data["messages"]) >= 2  # user + assistant

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, client: AsyncClient) -> None:
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.get(f"/api/v1/profiles/{pid}/chat/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_conversation_wrong_profile(self, client: AsyncClient) -> None:
        """Conversation from profile A not accessible via profile B."""
        _override_chat_deps()
        profile_a = await _create_profile(client)
        pid_a = profile_a["id"]

        # Create conversation on profile A
        resp1 = await client.post(
            f"/api/v1/profiles/{pid_a}/chat",
            data={"content": "Hello"},
        )
        convo_id = resp1.json()["message"]["conversation_id"]

        # Create profile B
        resp_b = await client.post(
            "/api/v1/profiles",
            json={"name": "Other Profile", "relationship": "spouse"},
        )
        pid_b = resp_b.json()["id"]

        # Try to get profile A's conversation via profile B
        resp2 = await client.get(f"/api/v1/profiles/{pid_b}/chat/{convo_id}")
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_account_isolation(self, client: AsyncClient) -> None:
        """Other account cannot access chat conversations."""
        _override_chat_deps()
        profile = await _create_profile(client)
        pid = profile["id"]

        await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "Hello"},
        )

        # Switch to other account
        use_account(OTHER_ACCOUNT_ID)

        resp = await client.get(f"/api/v1/profiles/{pid}/chat")
        assert resp.status_code == 404  # profile not found for this account

    @pytest.mark.asyncio
    async def test_send_message_with_topic(self, client: AsyncClient) -> None:
        _override_chat_deps()
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "How to lower cholesterol?", "topic": "Cholesterol"},
        )
        assert resp.status_code == 201

        # Verify topic is set on conversation
        convo_id = resp.json()["message"]["conversation_id"]
        resp2 = await client.get(f"/api/v1/profiles/{pid}/chat/{convo_id}")
        assert resp2.json()["topic"] == "Cholesterol"


def _mock_memory_service() -> MagicMock:
    """Return a mock MemoryService for delete tests."""
    svc = MagicMock()
    svc.delete_by_source = AsyncMock(return_value=2)
    return svc


def _override_delete_deps() -> None:
    """Override deps for delete route tests (no LLM needed, just memory service)."""
    _override_chat_deps()
    app.dependency_overrides[get_memory_service] = _mock_memory_service


class TestDeleteConversation:
    @pytest.mark.asyncio
    async def test_delete_conversation(self, client: AsyncClient) -> None:
        _override_delete_deps()
        profile = await _create_profile(client)
        pid = profile["id"]

        # Create a conversation
        resp = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "Hello there"},
        )
        assert resp.status_code == 201
        convo_id = resp.json()["message"]["conversation_id"]

        # Delete it
        resp2 = await client.delete(f"/api/v1/profiles/{pid}/chat/{convo_id}")
        assert resp2.status_code == 204

        # Verify it's gone
        resp3 = await client.get(f"/api/v1/profiles/{pid}/chat/{convo_id}")
        assert resp3.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_conversation_not_found(self, client: AsyncClient) -> None:
        _override_delete_deps()
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.delete(f"/api/v1/profiles/{pid}/chat/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_conversation_wrong_profile(self, client: AsyncClient) -> None:
        _override_delete_deps()
        profile_a = await _create_profile(client)
        pid_a = profile_a["id"]

        # Create conversation on profile A
        resp = await client.post(
            f"/api/v1/profiles/{pid_a}/chat",
            data={"content": "Hello"},
        )
        convo_id = resp.json()["message"]["conversation_id"]

        # Create profile B
        resp_b = await client.post(
            "/api/v1/profiles",
            json={"name": "Other", "relationship": "spouse"},
        )
        pid_b = resp_b.json()["id"]

        # Try to delete A's conversation via B
        resp2 = await client.delete(f"/api/v1/profiles/{pid_b}/chat/{convo_id}")
        assert resp2.status_code == 404


class TestRenameConversation:
    @pytest.mark.asyncio
    async def test_rename_conversation(self, client: AsyncClient) -> None:
        _override_chat_deps()
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "Hello"},
        )
        convo_id = resp.json()["message"]["conversation_id"]

        resp2 = await client.patch(
            f"/api/v1/profiles/{pid}/chat/{convo_id}",
            json={"topic": "My new topic"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["topic"] == "My new topic"

    @pytest.mark.asyncio
    async def test_rename_conversation_not_found(self, client: AsyncClient) -> None:
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.patch(
            f"/api/v1/profiles/{pid}/chat/{uuid.uuid4()}",
            json={"topic": "Nope"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_rename_conversation_empty_topic(self, client: AsyncClient) -> None:
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.patch(
            f"/api/v1/profiles/{pid}/chat/{uuid.uuid4()}",
            json={"topic": ""},
        )
        assert resp.status_code == 422
