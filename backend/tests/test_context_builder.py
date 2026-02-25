from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.context_builder import (
    ContextBuilder,
    ContextResult,
    _extract_date_prefix,
    _format_allergy,
    _format_condition,
    _format_medication,
    format_memories_section,
    format_profile_section,
)
from app.services.memory import MemoryService, count_tokens

PROFILE_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_profile(**overrides: object) -> MagicMock:
    """Create a mock Profile ORM object with realistic health data."""
    profile = MagicMock()
    profile.id = overrides.pop("id", PROFILE_ID)
    profile.name = overrides.pop("name", "Chen Wei")
    profile.relationship = overrides.pop("relationship", "parent")
    profile.sex = overrides.pop("sex", "female")
    profile.date_of_birth = overrides.pop("date_of_birth", date(1964, 3, 15))
    profile.blood_type = overrides.pop("blood_type", "A+")
    profile.allergies = overrides.pop(
        "allergies",
        [
            {"allergen": "Penicillin", "severity": "severe", "reaction": "anaphylaxis risk"},
            {"allergen": "Shellfish", "severity": "mild", "reaction": "hives"},
        ],
    )
    profile.current_medications = overrides.pop(
        "current_medications",
        [
            {"name": "Metformin", "dosage": "500mg", "frequency": "twice daily"},
            {"name": "Lisinopril", "dosage": "10mg", "frequency": "once daily"},
        ],
    )
    profile.medical_conditions = overrides.pop(
        "medical_conditions",
        [
            {"condition": "Type 2 Diabetes", "diagnosed": "2019", "status": "active"},
            {"condition": "Hypertension", "diagnosed": "2020", "status": "managed"},
        ],
    )
    profile.family_medical_history = overrides.pop(
        "family_medical_history",
        {"Heart Disease": ["Father (heart attack at 55)"], "Diabetes": ["Maternal grandmother"]},
    )
    for k, v in overrides.items():
        setattr(profile, k, v)
    return profile


def _make_mock_memories() -> list[dict]:
    return [
        {
            "id": "mem-1",
            "memory": "Diagnosed with UTI, treated with Ciprofloxacin, resolved",
            "metadata": {"category": "diagnoses"},
            "score": 0.92,
            "created_at": "2026-02-10T08:00:00Z",
            "updated_at": "2026-02-10T08:00:00Z",
        },
        {
            "id": "mem-2",
            "memory": "HbA1c was 7.2%, doctor recommended increasing Metformin",
            "metadata": {"category": "lab_results"},
            "score": 0.85,
            "created_at": "2026-01-15T10:30:00Z",
            "updated_at": "2026-01-15T10:30:00Z",
        },
        {
            "id": "mem-3",
            "memory": "Reported persistent knee pain, X-ray showed early osteoarthritis",
            "metadata": {"category": "symptoms"},
            "score": 0.78,
            "created_at": "2025-12-01T14:00:00Z",
            "updated_at": "2025-12-01T14:00:00Z",
        },
    ]


# ---------------------------------------------------------------------------
# _format_allergy
# ---------------------------------------------------------------------------


def test_format_allergy_full() -> None:
    result = _format_allergy(
        {"allergen": "Penicillin", "severity": "severe", "reaction": "anaphylaxis"}
    )
    assert result == "Penicillin (severe — anaphylaxis)"


def test_format_allergy_severity_only() -> None:
    result = _format_allergy({"allergen": "Dust", "severity": "mild"})
    assert result == "Dust (mild)"


def test_format_allergy_reaction_only() -> None:
    result = _format_allergy({"allergen": "Pollen", "reaction": "sneezing"})
    assert result == "Pollen (sneezing)"


def test_format_allergy_no_details() -> None:
    result = _format_allergy({"allergen": "Latex"})
    assert result == "Latex"


# ---------------------------------------------------------------------------
# _format_medication
# ---------------------------------------------------------------------------


def test_format_medication_full() -> None:
    result = _format_medication(
        {"name": "Metformin", "dosage": "500mg", "frequency": "twice daily"}
    )
    assert result == "Metformin 500mg, twice daily"


def test_format_medication_name_only() -> None:
    result = _format_medication({"name": "Aspirin"})
    assert result == "Aspirin"


def test_format_medication_no_frequency() -> None:
    result = _format_medication({"name": "Ibuprofen", "dosage": "200mg"})
    assert result == "Ibuprofen 200mg"


# ---------------------------------------------------------------------------
# _format_condition
# ---------------------------------------------------------------------------


def test_format_condition_full() -> None:
    result = _format_condition(
        {"condition": "Type 2 Diabetes", "diagnosed": "2019", "status": "active"}
    )
    assert result == "Type 2 Diabetes (diagnosed 2019, active)"


def test_format_condition_status_only() -> None:
    result = _format_condition({"condition": "Asthma", "status": "managed"})
    assert result == "Asthma (managed)"


def test_format_condition_bare() -> None:
    result = _format_condition({"condition": "Migraine"})
    assert result == "Migraine"


# ---------------------------------------------------------------------------
# _extract_date_prefix
# ---------------------------------------------------------------------------


def test_extract_date_prefix_iso_string() -> None:
    assert _extract_date_prefix("2026-02-10T08:00:00Z") == "[Feb 2026] "


def test_extract_date_prefix_empty() -> None:
    assert _extract_date_prefix("") == ""


def test_extract_date_prefix_none() -> None:
    assert _extract_date_prefix(None) == ""


def test_extract_date_prefix_datetime_object() -> None:
    from datetime import datetime

    dt = datetime(2025, 12, 1, 14, 0, 0)
    assert _extract_date_prefix(dt) == "[Dec 2025] "


# ---------------------------------------------------------------------------
# format_profile_section
# ---------------------------------------------------------------------------


def test_format_profile_section_full_data() -> None:
    profile = _make_mock_profile()
    from app.services.memory_extractor import load_profile_context

    ctx = load_profile_context(profile)
    ctx["relationship"] = profile.relationship

    section = format_profile_section(ctx)

    assert "## Patient Profile" in section
    assert "Chen Wei" in section
    assert "female" in section
    assert "Relationship to user: parent" in section
    assert "Blood type: A+" in section

    # Allergies
    assert "## Known Allergies" in section
    assert "Penicillin (severe — anaphylaxis risk)" in section
    assert "Shellfish (mild — hives)" in section

    # Medications
    assert "## Current Medications" in section
    assert "Metformin 500mg, twice daily" in section
    assert "Lisinopril 10mg, once daily" in section

    # Conditions
    assert "## Medical Conditions" in section
    assert "Type 2 Diabetes (diagnosed 2019, active)" in section
    assert "Hypertension (diagnosed 2020, managed)" in section

    # Family history
    assert "## Family Medical History" in section
    assert "Heart Disease: Father (heart attack at 55)" in section
    assert "Diabetes: Maternal grandmother" in section


def test_format_profile_section_empty_optional_fields() -> None:
    profile = _make_mock_profile(
        sex=None,
        date_of_birth=None,
        blood_type=None,
        allergies=[],
        current_medications=[],
        medical_conditions=[],
        family_medical_history={},
        relationship=None,
    )
    from app.services.memory_extractor import load_profile_context

    ctx = load_profile_context(profile)
    section = format_profile_section(ctx)

    assert "Age: Unknown" in section
    assert "Sex: Not specified" in section
    assert "Blood type" not in section
    assert "Relationship to user" not in section
    assert "None known" in section  # allergies + conditions
    assert "None reported" in section  # family history


# ---------------------------------------------------------------------------
# format_memories_section
# ---------------------------------------------------------------------------


def test_format_memories_section_with_data() -> None:
    memories = _make_mock_memories()
    result = format_memories_section(memories)

    assert "[Feb 2026] Diagnosed with UTI" in result
    assert "[Jan 2026] HbA1c was 7.2%" in result
    assert "[Dec 2025] Reported persistent knee pain" in result


def test_format_memories_section_empty() -> None:
    result = format_memories_section([])
    assert result == "No relevant history found."


def test_format_memories_section_no_timestamps() -> None:
    memories = [{"memory": "Has chronic back pain"}]
    result = format_memories_section(memories)
    assert result == "- Has chronic back pain"


# ---------------------------------------------------------------------------
# Token budget enforcement
# ---------------------------------------------------------------------------


def test_memories_section_respects_token_budget() -> None:
    """A large memory list should be truncated when over budget."""
    # Create many memories to exceed a small budget
    memories = [
        {
            "memory": f"Long medical fact number {i} with extra detail about condition",
            "metadata": {"category": "medical_history"},
            "created_at": f"2026-01-{i + 1:02d}T00:00:00Z",
        }
        for i in range(50)
    ]
    section = format_memories_section(memories)
    original_tokens = count_tokens(section)

    # Simulate what ContextBuilder does: truncate to a small budget
    from app.services.memory import truncate_to_token_budget

    budget = 100
    assert original_tokens > budget, "Test requires memories to exceed budget"

    truncated = truncate_to_token_budget(section, budget)
    truncated_tokens = count_tokens(truncated)

    assert truncated_tokens <= budget + 20  # small overshoot from line-boundary logic
    assert "truncated for context limit" in truncated


# ---------------------------------------------------------------------------
# ContextBuilder.build — full pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_returns_context_result() -> None:
    profile = _make_mock_profile()
    memories = _make_mock_memories()

    mock_db = AsyncMock()
    mock_db.get.return_value = profile

    mock_mem0 = MagicMock()
    mock_mem0.search.return_value = {"results": memories}
    memory_service = MemoryService(mock_mem0)

    builder = ContextBuilder(memory_service)
    result = await builder.build(mock_db, PROFILE_ID, "knee pain", "chat")

    assert isinstance(result, ContextResult)
    assert result.memories_used == 3
    assert result.profile_context["name"] == "Chen Wei"
    assert result.profile_context["relationship"] == "parent"
    assert "profile" in result.token_counts
    assert "memories" in result.token_counts
    assert "total" in result.token_counts
    assert result.token_counts["total"] > 0


@pytest.mark.asyncio
async def test_build_prompt_contains_profile_and_memories() -> None:
    profile = _make_mock_profile()
    memories = _make_mock_memories()

    mock_db = AsyncMock()
    mock_db.get.return_value = profile

    mock_mem0 = MagicMock()
    mock_mem0.search.return_value = {"results": memories}
    memory_service = MemoryService(mock_mem0)

    builder = ContextBuilder(memory_service)
    result = await builder.build(mock_db, PROFILE_ID, "diabetes checkup", "chat")

    # Profile sections present
    assert "## Patient Profile" in result.system_prompt
    assert "Chen Wei" in result.system_prompt
    assert "Metformin 500mg, twice daily" in result.system_prompt
    assert "Penicillin (severe — anaphylaxis risk)" in result.system_prompt

    # Memories present
    assert "## Relevant History" in result.system_prompt
    assert "HbA1c was 7.2%" in result.system_prompt

    # Disclaimer present
    assert "MEDICAL DISCLAIMER" in result.system_prompt


@pytest.mark.asyncio
async def test_build_profile_not_found_raises() -> None:
    mock_db = AsyncMock()
    mock_db.get.return_value = None

    mock_mem0 = MagicMock()
    mock_mem0.search.return_value = {"results": []}
    memory_service = MemoryService(mock_mem0)

    builder = ContextBuilder(memory_service)
    with pytest.raises(ValueError, match="not found"):
        await builder.build(mock_db, PROFILE_ID, "test", "chat")


@pytest.mark.asyncio
async def test_build_no_memories() -> None:
    profile = _make_mock_profile()

    mock_db = AsyncMock()
    mock_db.get.return_value = profile

    mock_mem0 = MagicMock()
    mock_mem0.search.return_value = {"results": []}
    memory_service = MemoryService(mock_mem0)

    builder = ContextBuilder(memory_service)
    result = await builder.build(mock_db, PROFILE_ID, "hello", "chat")

    assert result.memories_used == 0
    assert "No relevant history found." in result.system_prompt


# ---------------------------------------------------------------------------
# Interaction type routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diagnosis_uses_broadest_retrieval() -> None:
    """Diagnosis should search with highest limit, no category filter."""
    profile = _make_mock_profile()

    mock_db = AsyncMock()
    mock_db.get.return_value = profile

    mock_mem0 = MagicMock()
    mock_mem0.search.return_value = {"results": []}
    memory_service = MemoryService(mock_mem0)

    builder = ContextBuilder(memory_service)
    await builder.build(mock_db, PROFILE_ID, "chest pain", "diagnosis")

    _, kwargs = mock_mem0.search.call_args
    assert kwargs["limit"] == 20
    assert kwargs.get("filters") is None  # no category restriction


@pytest.mark.asyncio
async def test_chat_uses_standard_retrieval() -> None:
    """Chat should search with default limit and no category filter."""
    profile = _make_mock_profile()

    mock_db = AsyncMock()
    mock_db.get.return_value = profile

    mock_mem0 = MagicMock()
    mock_mem0.search.return_value = {"results": []}
    memory_service = MemoryService(mock_mem0)

    builder = ContextBuilder(memory_service)
    await builder.build(mock_db, PROFILE_ID, "general health", "chat")

    call_kwargs = mock_mem0.search.call_args
    assert call_kwargs is not None
    _, kwargs = call_kwargs
    assert kwargs["limit"] == 10
    assert kwargs.get("filters") is None


@pytest.mark.asyncio
async def test_report_analysis_uses_lab_categories() -> None:
    """Report analysis should filter to lab/vitals/meds/history categories."""
    profile = _make_mock_profile()

    mock_db = AsyncMock()
    mock_db.get.return_value = profile

    mock_mem0 = MagicMock()
    mock_mem0.search.return_value = {"results": []}
    memory_service = MemoryService(mock_mem0)

    builder = ContextBuilder(memory_service)
    await builder.build(mock_db, PROFILE_ID, "blood test results", "report_analysis")

    _, kwargs = mock_mem0.search.call_args
    assert kwargs["limit"] == 10
    categories = kwargs["filters"]["category"]["in"]
    assert "lab_results" in categories
    assert "vitals" in categories
    assert "medications" in categories


# ---------------------------------------------------------------------------
# Unknown interaction type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_interaction_type_falls_back_to_chat() -> None:
    """Unknown interaction_type should fall through to chat-style retrieval."""
    profile = _make_mock_profile()

    mock_db = AsyncMock()
    mock_db.get.return_value = profile

    mock_mem0 = MagicMock()
    mock_mem0.search.return_value = {"results": []}
    memory_service = MemoryService(mock_mem0)

    builder = ContextBuilder(memory_service)
    result = await builder.build(mock_db, PROFILE_ID, "test", "unknown_type")

    # Should not raise — falls through to chat branch in retrieve_memories
    assert isinstance(result, ContextResult)
    _, kwargs = mock_mem0.search.call_args
    assert kwargs["limit"] == 10
    assert kwargs.get("filters") is None


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_degrades_gracefully_on_memory_failure() -> None:
    """If Mem0 is unavailable, build() should still return profile-only context."""
    profile = _make_mock_profile()

    mock_db = AsyncMock()
    mock_db.get.return_value = profile

    mock_mem0 = MagicMock()
    mock_mem0.search.side_effect = ConnectionError("Mem0 unavailable")
    memory_service = MemoryService(mock_mem0)

    builder = ContextBuilder(memory_service)
    result = await builder.build(mock_db, PROFILE_ID, "test query", "chat")

    # Should succeed with profile data, zero memories
    assert isinstance(result, ContextResult)
    assert result.memories_used == 0
    assert "No relevant history found." in result.system_prompt
    assert "Chen Wei" in result.system_prompt
    assert "Metformin 500mg, twice daily" in result.system_prompt


# ---------------------------------------------------------------------------
# Custom template
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_custom_template() -> None:
    profile = _make_mock_profile()

    mock_db = AsyncMock()
    mock_db.get.return_value = profile

    mock_mem0 = MagicMock()
    mock_mem0.search.return_value = {"results": []}
    memory_service = MemoryService(mock_mem0)

    custom = "Custom system.\n{profile_section}\n---\n{memories_section}"
    builder = ContextBuilder(memory_service)
    result = await builder.build(mock_db, PROFILE_ID, "test", "chat", template=custom)

    assert result.system_prompt.startswith("Custom system.")
    assert "## Patient Profile" in result.system_prompt
    assert "MEDICAL DISCLAIMER" not in result.system_prompt


# ---------------------------------------------------------------------------
# Token budget in build()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_enforces_memory_budget() -> None:
    profile = _make_mock_profile()
    # Create many large memories
    big_memories = [
        {
            "id": f"mem-{i}",
            "memory": f"Detailed medical fact #{i}: " + "x" * 200,
            "metadata": {"category": "medical_history"},
            "score": 0.9 - i * 0.01,
            "created_at": f"2026-01-{i + 1:02d}T00:00:00Z",
        }
        for i in range(30)
    ]

    mock_db = AsyncMock()
    mock_db.get.return_value = profile

    mock_mem0 = MagicMock()
    mock_mem0.search.return_value = {"results": big_memories}
    memory_service = MemoryService(mock_mem0)

    builder = ContextBuilder(memory_service)
    result = await builder.build(mock_db, PROFILE_ID, "test", "chat", memory_budget=200)

    # Memory tokens should be within budget (with small tolerance for line-truncation)
    assert result.token_counts["memories"] <= 220
    assert "truncated for context limit" in result.system_prompt
    # memories_used should reflect injected count, not retrieved count
    assert result.memories_used < 30
