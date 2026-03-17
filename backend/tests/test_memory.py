from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient

from app.services.memory import (
    MemoryService,
    build_conversation_window,
    build_mem0_config,
    count_tokens,
    truncate_to_token_budget,
)
from app.services.memory_extractor import (
    assemble_system_prompt,
    enrich_messages_with_date,
    load_profile_context,
)

# Minimal template for testing assemble_system_prompt (the real chat prompt
# lives in chat_prompts.py and uses a different template format).
_TEST_TEMPLATE = """You are a friendly health assistant for {profile_name}.

## MEDICAL DISCLAIMER
You provide general health information, NOT medical diagnoses.

## PATIENT PROFILE
- Age: {age} | Sex: {sex}
- Allergies: {allergies}
- Medications: {medications}
- Conditions: {conditions}

## RELEVANT CONTEXT
{episodic_memories}"""

PROFILE_ID = uuid.uuid4()

BASE = "/api/v1/profiles"


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_mem0() -> MagicMock:
    client = MagicMock()
    client.add.return_value = {
        "results": [{"id": "mem-1", "memory": "Has diabetes", "event": "ADD"}]
    }
    client.search.return_value = {
        "results": [
            {
                "id": "mem-1",
                "memory": "Has diabetes",
                "metadata": {"category": "diagnoses"},
                "score": 0.9,
            }
        ]
    }
    client.get_all.return_value = {
        "results": [
            {
                "id": "mem-1",
                "memory": "Has diabetes",
                "metadata": {"category": "diagnoses", "source": "chat"},
            }
        ]
    }
    client.get.return_value = {
        "id": "mem-1",
        "user_id": str(PROFILE_ID),
        "memory": "Has diabetes",
    }
    client.history.return_value = [{"id": "evt-1", "event": "ADD"}]
    client.delete.return_value = None
    client.delete_all.return_value = None
    return client


@pytest.fixture
def memory_service(mock_mem0: MagicMock) -> MemoryService:
    return MemoryService(mock_mem0)


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _create_profile(client: AsyncClient, **overrides: object) -> dict:
    payload = {"name": "Test User", "relationship": "self", **overrides}
    resp = await client.post(BASE, json=payload)
    assert resp.status_code == 201
    return resp.json()


# ── Unit tests: MemoryService.add ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_passes_profile_id_as_user_id(
    memory_service: MemoryService, mock_mem0: MagicMock
) -> None:
    await memory_service.add(PROFILE_ID, "test messages")
    mock_mem0.add.assert_called_once()
    _, kwargs = mock_mem0.add.call_args
    assert kwargs["user_id"] == str(PROFILE_ID)


@pytest.mark.asyncio
async def test_add_passes_metadata_with_category(
    memory_service: MemoryService, mock_mem0: MagicMock
) -> None:
    await memory_service.add(PROFILE_ID, "taking aspirin", category="medications", source="chat")
    _, kwargs = mock_mem0.add.call_args
    assert kwargs["metadata"]["category"] == "medications"
    assert kwargs["metadata"]["source"] == "chat"


@pytest.mark.asyncio
async def test_add_default_source(memory_service: MemoryService, mock_mem0: MagicMock) -> None:
    await memory_service.add(PROFILE_ID, "some fact")
    _, kwargs = mock_mem0.add.call_args
    assert kwargs["metadata"]["source"] == "conversation"


# ── Unit tests: MemoryService.search ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_returns_results(memory_service: MemoryService) -> None:
    results = await memory_service.search(PROFILE_ID, "diabetes")
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["memory"] == "Has diabetes"


@pytest.mark.asyncio
async def test_search_forwards_threshold(
    memory_service: MemoryService, mock_mem0: MagicMock
) -> None:
    await memory_service.search(PROFILE_ID, "diabetes", threshold=0.3)
    _, kwargs = mock_mem0.search.call_args
    assert kwargs["threshold"] == 0.3


@pytest.mark.asyncio
async def test_search_with_single_category_filter(
    memory_service: MemoryService, mock_mem0: MagicMock
) -> None:
    """Single category uses exact equality filter (pgvector compatible)."""
    await memory_service.search(PROFILE_ID, "meds", categories=["medications"])
    _, kwargs = mock_mem0.search.call_args
    assert kwargs["filters"] == {"category": "medications"}


@pytest.mark.asyncio
async def test_search_with_multi_category_filter(
    memory_service: MemoryService, mock_mem0: MagicMock
) -> None:
    """Multiple categories search each separately and merge results."""
    await memory_service.search(PROFILE_ID, "meds", categories=["medications", "allergies"])
    # Should be called twice — once per category
    assert mock_mem0.search.call_count == 2
    calls = mock_mem0.search.call_args_list
    assert calls[0][1]["filters"] == {"category": "medications"}
    assert calls[1][1]["filters"] == {"category": "allergies"}


# ── Unit tests: MemoryService.get_all ────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_all_returns_results(memory_service: MemoryService) -> None:
    results = await memory_service.get_all(PROFILE_ID)
    assert isinstance(results, list)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_get_all_with_category(memory_service: MemoryService, mock_mem0: MagicMock) -> None:
    await memory_service.get_all(PROFILE_ID, category="medications")
    _, kwargs = mock_mem0.get_all.call_args
    assert kwargs["filters"] == {"category": "medications"}


# ── Unit tests: MemoryService.get_history ────────────────────────────────────


@pytest.mark.asyncio
async def test_get_history(memory_service: MemoryService) -> None:
    history = await memory_service.get_history("mem-1")
    assert isinstance(history, list)
    assert history[0]["id"] == "evt-1"


# ── Unit tests: MemoryService.delete ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_verifies_ownership(
    memory_service: MemoryService, mock_mem0: MagicMock
) -> None:
    other_id = uuid.uuid4()
    mock_mem0.get.return_value = {
        "id": "mem-1",
        "user_id": str(other_id),
        "memory": "Has diabetes",
    }
    with pytest.raises(ValueError, match="does not belong to this profile"):
        await memory_service.delete(PROFILE_ID, "mem-1")


@pytest.mark.asyncio
async def test_delete_succeeds_for_owned_memory(
    memory_service: MemoryService, mock_mem0: MagicMock
) -> None:
    # mock_mem0.get already returns user_id == PROFILE_ID by default
    await memory_service.delete(PROFILE_ID, "mem-1")
    mock_mem0.delete.assert_called_once_with("mem-1")


# ── Unit tests: MemoryService.delete_all ─────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_all(memory_service: MemoryService, mock_mem0: MagicMock) -> None:
    await memory_service.delete_all(PROFILE_ID)
    mock_mem0.delete_all.assert_called_once()
    _, kwargs = mock_mem0.delete_all.call_args
    assert kwargs["user_id"] == str(PROFILE_ID)


# ── Unit tests: MemoryService.delete_by_source ───────────────────────────────


@pytest.mark.asyncio
async def test_delete_by_source(memory_service: MemoryService, mock_mem0: MagicMock) -> None:
    mock_mem0.get_all.return_value = {
        "results": [
            {"id": "mem-1", "memory": "fact 1", "metadata": {"source": "diagnosis:session-abc"}},
            {"id": "mem-2", "memory": "fact 2", "metadata": {"source": "diagnosis:session-abc"}},
        ]
    }
    deleted = await memory_service.delete_by_source(PROFILE_ID, "diagnosis:session-abc")
    assert deleted == 2

    # Verify get_all was called with the source filter
    _, kwargs = mock_mem0.get_all.call_args
    assert kwargs["user_id"] == str(PROFILE_ID)
    assert kwargs["filters"] == {"source": "diagnosis:session-abc"}

    # Verify each memory was deleted
    assert mock_mem0.delete.call_count == 2
    mock_mem0.delete.assert_any_call("mem-1")
    mock_mem0.delete.assert_any_call("mem-2")


@pytest.mark.asyncio
async def test_delete_by_source_skips_wrong_source(
    memory_service: MemoryService, mock_mem0: MagicMock
) -> None:
    """If Mem0 ignores the filter and returns all memories, only matching ones are deleted."""
    mock_mem0.get_all.return_value = {
        "results": [
            {"id": "mem-1", "memory": "right", "metadata": {"source": "chat:abc"}},
            {"id": "mem-2", "memory": "wrong", "metadata": {"source": "chat:other"}},
            {"id": "mem-3", "memory": "no meta", "metadata": {}},
        ]
    }
    deleted = await memory_service.delete_by_source(PROFILE_ID, "chat:abc")
    assert deleted == 1
    mock_mem0.delete.assert_called_once_with("mem-1")


@pytest.mark.asyncio
async def test_delete_by_source_empty(memory_service: MemoryService, mock_mem0: MagicMock) -> None:
    mock_mem0.get_all.return_value = {"results": []}
    deleted = await memory_service.delete_by_source(PROFILE_ID, "chat:no-such-id")
    assert deleted == 0
    mock_mem0.delete.assert_not_called()


# ── Unit tests: extract helpers ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_raw_stores_with_correct_metadata(
    memory_service: MemoryService, mock_mem0: MagicMock
) -> None:
    """add_raw (used by save_to_memory tool) stores with infer=False."""
    mock_mem0.add.return_value = {"results": [{"id": "m1", "memory": "test", "event": "ADD"}]}
    await memory_service.add_raw(
        PROFILE_ID, "Takes metformin 500mg twice daily", category="medications", source="chat:c1"
    )
    _, kwargs = mock_mem0.add.call_args
    assert kwargs["metadata"]["source"] == "chat:c1"
    assert kwargs["metadata"]["category"] == "medications"
    assert kwargs["infer"] is False


# ── Mem0 config tests ────────────────────────────────────────────────────────


def test_build_mem0_config_uses_gemini_embedder() -> None:
    from app.core.config import Settings

    s = Settings(gemini_api_key="test-gemini-key", qwen_api_key="test-qwen-key")
    config = build_mem0_config(s)
    assert config["embedder"]["provider"] == "gemini"
    assert config["embedder"]["config"]["api_key"] == "test-gemini-key"
    assert config["embedder"]["config"]["model"] == "models/gemini-embedding-001"
    assert config["vector_store"]["config"]["hnsw"] is True


# ── Memory extractor tests ──────────────────────────────────────────────────


def test_enrich_messages_with_date() -> None:
    msgs = [{"role": "user", "content": "I have a headache"}]
    enriched = enrich_messages_with_date(msgs)
    assert len(enriched) == 2
    assert enriched[0]["role"] == "system"
    assert "Today's date is" in enriched[0]["content"]
    assert enriched[1] == msgs[0]


def test_load_profile_context() -> None:
    from datetime import date
    from unittest.mock import MagicMock as Mock

    profile = Mock()
    profile.name = "Mom"
    profile.sex = "female"
    profile.date_of_birth = date(1965, 5, 20)
    profile.blood_type = "A+"
    profile.allergies = [{"allergen": "penicillin", "severity": "severe"}]
    profile.current_medications = [{"name": "metformin", "dosage": "500mg"}]
    profile.medical_conditions = [{"condition": "diabetes", "status": "active"}]
    profile.family_medical_history = {"father": ["heart disease"]}

    ctx = load_profile_context(profile)
    assert ctx["name"] == "Mom"
    assert ctx["sex"] == "female"
    assert isinstance(ctx["age"], int)
    assert ctx["age"] > 50
    assert ctx["blood_type"] == "A+"
    assert ctx["allergies"] == profile.allergies
    assert ctx["current_medications"] == profile.current_medications


def test_assemble_system_prompt_formats_correctly() -> None:
    ctx = {
        "name": "Mom",
        "age": 60,
        "sex": "female",
        "allergies": [{"allergen": "penicillin"}],
        "current_medications": [{"name": "metformin"}],
        "medical_conditions": [{"condition": "diabetes"}],
    }
    memories = [
        {"memory": "Has type 2 diabetes", "metadata": {"category": "diagnoses"}},
        {"memory": "Takes metformin 500mg", "metadata": {"category": "medications"}},
    ]
    prompt = assemble_system_prompt(_TEST_TEMPLATE, ctx, memories, token_budget=500)
    assert "Mom" in prompt
    assert "60" in prompt
    assert "female" in prompt
    assert "penicillin" in prompt
    assert "[diagnoses] Has type 2 diabetes" in prompt
    assert "[medications] Takes metformin 500mg" in prompt
    assert "MEDICAL DISCLAIMER" in prompt


def test_assemble_system_prompt_empty_memories() -> None:
    ctx = {
        "name": "Test",
        "age": None,
        "sex": None,
        "allergies": [],
        "current_medications": [],
        "medical_conditions": [],
    }
    prompt = assemble_system_prompt(_TEST_TEMPLATE, ctx, [], token_budget=500)
    assert "No prior context." in prompt
    assert "Unknown" in prompt  # age and sex default to Unknown


# ── Token utility tests ─────────────────────────────────────────────────────


def test_count_tokens() -> None:
    result = count_tokens("Hello world")
    assert isinstance(result, int)
    assert result > 0


def test_truncate_no_truncation() -> None:
    short_text = "Short text within budget"
    result = truncate_to_token_budget(short_text, max_tokens=100)
    assert result == short_text


def test_truncate_applies_budget() -> None:
    long_text = "word " * 500
    result = truncate_to_token_budget(long_text, max_tokens=10)
    assert len(result) < len(long_text)
    assert result.endswith("[... additional history truncated for context limit]")


def test_build_conversation_window_preserves_first() -> None:
    messages = [
        {"role": "system", "content": "You are a doctor."},
        {"role": "user", "content": "msg 1"},
        {"role": "assistant", "content": "reply 1"},
        {"role": "user", "content": "msg 2"},
        {"role": "assistant", "content": "reply 2"},
    ]
    # Use a small budget so not all messages fit
    result = build_conversation_window(messages, max_tokens=30)
    assert result[0] == messages[0]
    assert len(result) >= 1


def test_build_conversation_window_empty() -> None:
    result = build_conversation_window([], max_tokens=100)
    assert result == []


# ── API tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_memory_summary(client: AsyncClient, mock_mem0: MagicMock) -> None:
    from app.api.deps import get_memory_service
    from app.main import app

    profile = await _create_profile(client)
    pid = profile["id"]

    svc = MemoryService(mock_mem0)
    app.dependency_overrides[get_memory_service] = lambda: svc

    resp = await client.get(f"{BASE}/{pid}/memory")
    assert resp.status_code == 200
    data = resp.json()
    assert data["profile_id"] == pid
    assert "facts_count" in data
    assert "memories" in data
    assert isinstance(data["memories"], list)

    del app.dependency_overrides[get_memory_service]


@pytest.mark.asyncio
async def test_list_facts(client: AsyncClient, mock_mem0: MagicMock) -> None:
    from app.api.deps import get_memory_service
    from app.main import app

    profile = await _create_profile(client)
    pid = profile["id"]

    svc = MemoryService(mock_mem0)
    app.dependency_overrides[get_memory_service] = lambda: svc

    resp = await client.get(f"{BASE}/{pid}/memory/facts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["profile_id"] == pid
    assert "facts" in data
    assert isinstance(data["facts"], list)

    del app.dependency_overrides[get_memory_service]


@pytest.mark.asyncio
async def test_list_facts_with_category_filter(client: AsyncClient, mock_mem0: MagicMock) -> None:
    from app.api.deps import get_memory_service
    from app.main import app

    profile = await _create_profile(client)
    pid = profile["id"]

    svc = MemoryService(mock_mem0)
    app.dependency_overrides[get_memory_service] = lambda: svc

    resp = await client.get(f"{BASE}/{pid}/memory/facts?category=medications")
    assert resp.status_code == 200

    # Verify the service was called with the category filter
    _, kwargs = mock_mem0.get_all.call_args
    assert kwargs["filters"] == {"category": "medications"}

    del app.dependency_overrides[get_memory_service]


@pytest.mark.asyncio
async def test_delete_memory_204(client: AsyncClient, mock_mem0: MagicMock) -> None:
    from app.api.deps import get_memory_service
    from app.main import app

    profile = await _create_profile(client)
    pid = profile["id"]

    # Make the ownership check pass for this profile
    mock_mem0.get.return_value = {
        "id": "mem-1",
        "user_id": pid,
        "memory": "Has diabetes",
    }
    svc = MemoryService(mock_mem0)
    app.dependency_overrides[get_memory_service] = lambda: svc

    resp = await client.delete(f"{BASE}/{pid}/memory/mem-1")
    assert resp.status_code == 204

    del app.dependency_overrides[get_memory_service]


@pytest.mark.asyncio
async def test_delete_memory_wrong_owner_returns_404(
    client: AsyncClient, mock_mem0: MagicMock
) -> None:
    from app.api.deps import get_memory_service
    from app.main import app

    profile = await _create_profile(client)
    pid = profile["id"]

    # Make the ownership check fail — memory belongs to a different profile
    mock_mem0.get.return_value = {
        "id": "mem-1",
        "user_id": str(uuid.uuid4()),
        "memory": "Not mine",
    }
    svc = MemoryService(mock_mem0)
    app.dependency_overrides[get_memory_service] = lambda: svc

    resp = await client.delete(f"{BASE}/{pid}/memory/mem-1")
    assert resp.status_code == 404

    del app.dependency_overrides[get_memory_service]
