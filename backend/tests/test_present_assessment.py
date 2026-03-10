"""Tests for the present_assessment tool and assessment formatting."""

from __future__ import annotations

import pytest

from app.agents.tools.present_assessment import build_present_assessment_tool
from app.services.diagnosis import _format_assessment_text
from app.services.message_parts_builder import _build_assessment_part


SAMPLE_ARGS = {
    "conditions": [
        {
            "name": "Tension-type headache",
            "confidence": "most_likely",
            "reasoning": "Band-like pressure across the forehead, bilateral.",
            "confirming_tests": "Neurological exam if recurring",
        },
        {
            "name": "Migraine without aura",
            "confidence": "possible",
            "reasoning": "Photophobia overlaps but pressure quality makes this less likely.",
        },
    ],
    "self_care": [
        {"action": "Rest in a dark, quiet room"},
        {"action": "Apply a cool compress to your forehead", "detail": "15 minutes on, 15 off"},
    ],
    "medications": [
        {"name": "Ibuprofen", "dosage": "400mg every 6 hours with food", "notes": "Avoid on empty stomach"},
        {"name": "Acetaminophen", "dosage": "500mg if ibuprofen unavailable"},
    ],
    "tests": [
        {"name": "Blood pressure check", "reason": "Hypertension can cause headaches", "urgency": "Next visit"},
    ],
    "warnings": [
        "Sudden severe worsening (worst headache of your life)",
        "Fever with stiff neck",
    ],
    "follow_up": "If headaches persist more than 3 days, see your doctor.",
    "sources": [
        {"title": "Mayo Clinic — Tension Headache", "url": "https://www.mayoclinic.org/diseases-conditions/tension-headache"},
    ],
}


@pytest.mark.asyncio
async def test_handler_echoes_args():
    tool = build_present_assessment_tool()
    assert tool.name == "present_assessment"
    assert tool.terminal is True

    result = await tool.handler(**SAMPLE_ARGS)
    assert result["status"] == "assessment_presented"
    assert len(result["conditions"]) == 2
    assert result["conditions"][0]["name"] == "Tension-type headache"
    assert result["medications"][0]["name"] == "Ibuprofen"
    assert len(result["warnings"]) == 2


@pytest.mark.asyncio
async def test_handler_defaults_empty_lists():
    tool = build_present_assessment_tool()
    result = await tool.handler(conditions=[{"name": "Test", "confidence": "possible", "reasoning": "r"}])
    assert result["self_care"] == []
    assert result["medications"] == []
    assert result["tests"] == []
    assert result["warnings"] == []
    assert result["sources"] == []
    assert result["follow_up"] is None


def test_format_assessment_text_contains_sections():
    text = _format_assessment_text(SAMPLE_ARGS)
    assert "## Assessment" in text
    assert "Most likely: Tension-type headache" in text
    assert "Also possible: Migraine without aura" in text
    assert "## What You Can Do Now" in text
    assert "**Ibuprofen** 400mg every 6 hours with food" in text
    assert "Avoid on empty stomach" in text
    assert "## Tests to Consider" in text
    assert "Blood pressure check" in text
    assert "## Watch For" in text
    assert "Fever with stiff neck" in text
    assert "## Follow-up" in text
    assert "Sources" in text
    assert "Mayo Clinic" in text


def test_format_assessment_text_minimal():
    text = _format_assessment_text({
        "conditions": [{"name": "Sprain", "confidence": "most_likely", "reasoning": "Twisted ankle."}],
    })
    assert "## Assessment" in text
    assert "Most likely: Sprain" in text
    # No other sections should appear
    assert "## What You Can Do Now" not in text
    assert "## Tests" not in text
    assert "## Watch For" not in text


def test_build_assessment_part():
    part = _build_assessment_part(SAMPLE_ARGS)
    assert part.type == "assessment"
    assert len(part.conditions) == 2
    assert part.conditions[0].name == "Tension-type headache"
    assert part.conditions[0].confidence == "most_likely"
    assert len(part.medications) == 2
    assert part.medications[0].dosage == "400mg every 6 hours with food"
    assert len(part.self_care) == 2
    assert len(part.tests) == 1
    assert len(part.warnings) == 2
    assert part.follow_up == "If headaches persist more than 3 days, see your doctor."
    assert len(part.sources) == 1


def test_build_assessment_part_empty():
    part = _build_assessment_part({"conditions": []})
    assert part.type == "assessment"
    assert part.conditions == []
    assert part.medications == []
    assert part.self_care == []
    assert part.warnings == []
    assert part.follow_up is None


def test_build_assistant_parts_with_assessment_skips_text():
    """When present_assessment tool was called, TextPart should be skipped."""
    from app.services.message_parts_builder import PartsAccumulator, build_assistant_parts
    from app.schemas.message_parts import ToolCallPart, ToolResultPart

    acc = PartsAccumulator()
    # Simulate a present_assessment tool call
    acc.tool_calls.append(ToolCallPart(
        id="tc_1", name="present_assessment", arguments=SAMPLE_ARGS
    ))
    acc.tool_results.append(ToolResultPart(
        call_id="tc_1", name="present_assessment",
        output={"status": "assessment_presented", **SAMPLE_ARGS}
    ))

    parts = build_assistant_parts("some fallback text", acc)

    # Should have NO text part (assessment replaces it)
    types = [p["type"] for p in parts]
    assert "text" not in types, f"TextPart should be skipped when assessment present: {types}"
    assert "assessment" in types
    # Assessment should have correct data
    assessment = next(p for p in parts if p["type"] == "assessment")
    assert len(assessment["conditions"]) == 2


def test_build_assistant_parts_without_assessment_has_text():
    """Without present_assessment, TextPart should be present as usual."""
    from app.services.message_parts_builder import PartsAccumulator, build_assistant_parts

    acc = PartsAccumulator()
    parts = build_assistant_parts("hello world", acc)
    types = [p["type"] for p in parts]
    assert "text" in types


def test_state_from_assessment_tool():
    from app.services.diagnosis import DiagnosisService

    state = DiagnosisService._state_from_assessment_tool(SAMPLE_ARGS, turn_number=5)
    assert state.phase == "differential"
    assert state.turn_number == 5
    assert state.ready_for_differential is True
    assert len(state.differential_diagnoses) == 2

    d0 = state.differential_diagnoses[0]
    assert d0.condition == "Tension-type headache"
    assert d0.confidence == 0.8
    assert "Band-like pressure" in d0.reasoning
    assert d0.urgency == "see_doctor_this_week"

    d1 = state.differential_diagnoses[1]
    assert d1.condition == "Migraine without aura"
    assert d1.confidence == 0.5
    assert d1.urgency == "see_doctor_soon"
