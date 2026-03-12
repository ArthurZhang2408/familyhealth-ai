"""Present assessment tool — emits structured diagnosis assessments."""

from __future__ import annotations

from typing import Any

from app.agents.types import ToolDefinition


def build_present_assessment_tool() -> ToolDefinition:
    """Create a ToolDefinition that presents a structured diagnosis assessment."""

    async def _handler(
        conditions: list[dict[str, Any]],
        self_care: list[dict[str, Any]] | None = None,
        medications: list[dict[str, Any]] | None = None,
        tests: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
        follow_up: str | None = None,
        sources: list[dict[str, Any]] | None = None,
        **_kwargs: Any,
    ) -> dict:
        return {
            "status": "assessment_presented",
            "conditions": conditions,
            "self_care": self_care or [],
            "medications": medications or [],
            "tests": tests or [],
            "warnings": warnings or [],
            "follow_up": follow_up,
            "sources": sources or [],
        }

    return ToolDefinition(
        name="present_assessment",
        terminal=True,
        description=(
            "Present your final diagnosis assessment to the user as a structured "
            "report. Call this ONCE when you have gathered enough information and "
            "are ready to deliver your differential diagnosis, self-care advice, "
            "medication recommendations, suggested tests, and warning signs. "
            "Do NOT write the assessment as free text — always use this tool."
        ),
        parameters={
            "type": "object",
            "properties": {
                "conditions": {
                    "type": "array",
                    "description": ("Ranked differential diagnosis. Most likely condition first."),
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": (
                                    "Condition name in plain language with medical term. "
                                    "E.g. 'Tension-type headache'"
                                ),
                            },
                            "confidence": {
                                "type": "string",
                                "enum": ["most_likely", "possible", "less_likely"],
                                "description": "How likely this diagnosis is",
                            },
                            "reasoning": {
                                "type": "string",
                                "description": (
                                    "Why this fits: which symptoms support it, "
                                    "which argue against. 2-4 sentences."
                                ),
                            },
                            "confirming_tests": {
                                "type": "string",
                                "description": ("What would confirm or rule out this condition"),
                            },
                        },
                        "required": ["name", "confidence", "reasoning"],
                    },
                },
                "self_care": {
                    "type": "array",
                    "description": "Actionable self-care and lifestyle advice",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "What to do. E.g. 'Rest in a dark, quiet room'",
                            },
                            "detail": {
                                "type": "string",
                                "description": "Additional context or instructions",
                            },
                        },
                        "required": ["action"],
                    },
                },
                "medications": {
                    "type": "array",
                    "description": (
                        "OTC medication recommendations. Check patient allergies "
                        "and current medications before recommending."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Medication name. E.g. 'Ibuprofen'",
                            },
                            "dosage": {
                                "type": "string",
                                "description": "Dosage and frequency. E.g. '400mg every 6 hours with food'",
                            },
                            "notes": {
                                "type": "string",
                                "description": "Warnings or extra context. E.g. 'Avoid on empty stomach'",
                            },
                        },
                        "required": ["name", "dosage"],
                    },
                },
                "tests": {
                    "type": "array",
                    "description": "Professional medical tests to consider",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Test name. E.g. 'CBC (Complete Blood Count)'",
                            },
                            "reason": {
                                "type": "string",
                                "description": "Why this test is recommended",
                            },
                            "urgency": {
                                "type": "string",
                                "description": "How soon. E.g. 'Within a week', 'If symptoms persist'",
                            },
                        },
                        "required": ["name", "reason"],
                    },
                },
                "warnings": {
                    "type": "array",
                    "description": (
                        "Warning signs that should prompt immediate medical attention. "
                        "Each item is a specific, actionable warning."
                    ),
                    "items": {"type": "string"},
                },
                "follow_up": {
                    "type": "string",
                    "description": (
                        "Follow-up guidance: when to check back, what to monitor, "
                        "upcoming appointments to schedule"
                    ),
                },
                "sources": {
                    "type": "array",
                    "description": "Citations from web search results used in the assessment",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Source title or description",
                            },
                            "url": {
                                "type": "string",
                                "description": "Source URL",
                            },
                        },
                        "required": ["title", "url"],
                    },
                },
            },
            "required": ["conditions"],
        },
        handler=_handler,
    )
