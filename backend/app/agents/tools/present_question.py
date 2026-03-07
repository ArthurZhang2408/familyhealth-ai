"""Present question tool — emits structured questions for the diagnosis agent."""

from __future__ import annotations

from typing import Any

from app.agents.types import ToolDefinition


def build_present_question_tool() -> ToolDefinition:
    """Create a ToolDefinition that presents structured questions to the user."""

    async def _handler(
        input_type: str,
        prompt: str,
        options: list[dict[str, Any]] | None = None,
        range: dict[str, Any] | None = None,
        **_kwargs: Any,
    ) -> dict:
        return {
            "status": "question_presented",
            "input_type": input_type,
            "prompt": prompt,
            "options": options,
            "range": range,
        }

    return ToolDefinition(
        name="present_question",
        terminal=True,
        description=(
            "Present a structured question to the user for symptom assessment. "
            "Use this instead of asking free-text questions. The user will see "
            "interactive UI (buttons, sliders, checkboxes) and tap their answer. "
            "Call this tool once per turn with the most important question."
        ),
        parameters={
            "type": "object",
            "properties": {
                "input_type": {
                    "type": "string",
                    "enum": ["multiple_choice", "scale", "yes_no", "multi_select"],
                    "description": (
                        "Type of input to present: "
                        "multiple_choice (pick one from options), "
                        "scale (numeric slider), "
                        "yes_no (binary choice), "
                        "multi_select (pick multiple from options)"
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": "The question to display to the user",
                },
                "options": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "Display text for the option",
                            },
                            "value": {
                                "type": "string",
                                "description": "Machine-readable value",
                            },
                        },
                        "required": ["label", "value"],
                    },
                    "description": "Options for multiple_choice or multi_select",
                },
                "range": {
                    "type": "object",
                    "properties": {
                        "min": {"type": "integer", "description": "Minimum value"},
                        "max": {"type": "integer", "description": "Maximum value"},
                        "step": {"type": "integer", "description": "Step increment (default 1)"},
                        "labels": {
                            "type": "object",
                            "properties": {
                                "min": {"type": "string"},
                                "max": {"type": "string"},
                            },
                            "description": "Labels for min and max ends of the scale",
                        },
                    },
                    "required": ["min", "max"],
                    "description": "Range config for scale input_type",
                },
            },
            "required": ["input_type", "prompt"],
        },
        handler=_handler,
    )
