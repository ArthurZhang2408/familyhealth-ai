"""Typed content parts for rich message persistence.

Messages store a `content_parts` JSONB array where each element is one of
these discriminated-union part types.  The plain-text `content` column is
kept as a denormalized fallback (search, backward compat).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel


class MessagePartType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    AGENT_STEPS = "agent_steps"
    MEMORY_CONTEXT = "memory_context"
    STRUCTURED_INPUT = "structured_input"


# ── Individual part models ───────────────────────────────────────────────


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImagePart(BaseModel):
    type: Literal["image"] = "image"
    url: str
    mime_type: str
    filename: str | None = None


class ToolCallPart(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    arguments: dict[str, Any]


class ToolResultPart(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    name: str
    output: dict[str, Any]
    is_error: bool = False
    summary: str | None = None


class AgentStepRecord(BaseModel):
    id: str
    message: str
    tool: str | None = None
    details: list[str] | None = None


class AgentStepsPart(BaseModel):
    type: Literal["agent_steps"] = "agent_steps"
    steps: list[AgentStepRecord]


class MemoryContextPart(BaseModel):
    type: Literal["memory_context"] = "memory_context"
    memories: list[dict[str, Any]]
    count: int = 0


class StructuredInputPart(BaseModel):
    """Phase 3 — structured question/answer for diagnosis."""

    type: Literal["structured_input"] = "structured_input"
    input_type: str  # "multiple_choice", "scale", "yes_no", "multi_select"
    prompt: str
    options: list[dict[str, Any]] | None = None
    range: dict[str, Any] | None = None
    selected: Any | None = None


# ── Union type ───────────────────────────────────────────────────────────

MessagePart = (
    TextPart
    | ImagePart
    | ToolCallPart
    | ToolResultPart
    | AgentStepsPart
    | MemoryContextPart
    | StructuredInputPart
)


def serialize_parts(parts: list[MessagePart]) -> list[dict[str, Any]]:
    """Serialize a list of MessagePart models to JSON-ready dicts."""
    return [p.model_dump() for p in parts]


def text_from_parts(parts: list[MessagePart]) -> str:
    """Extract plain text from parts (for the denormalized content column)."""
    texts = []
    for p in parts:
        if isinstance(p, TextPart):
            texts.append(p.text)
    return "\n".join(texts)
