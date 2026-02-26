"""LLM-agnostic types for the agent infrastructure."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


@dataclass
class ToolDefinition:
    """Declares a tool that an agent can invoke during execution."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    handler: Callable  # async (kwargs) -> dict

    def to_declaration(self) -> dict[str, Any]:
        """Convert to the function declaration format expected by LLM APIs."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


@dataclass
class ToolCall:
    """A tool invocation requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]

    @staticmethod
    def make_id() -> str:
        return f"tc_{uuid.uuid4().hex[:12]}"


@dataclass
class ToolResult:
    """The result of executing a tool call."""

    call_id: str
    name: str
    output: dict[str, Any]
    is_error: bool = False


class AgentEventType(StrEnum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    COMPLETE = "complete"


@dataclass
class AgentEvent:
    """An event emitted during agent execution (for observability / streaming)."""

    type: AgentEventType
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """The final result of an agent run."""

    content: str
    model: str
    usage: dict[str, int]
    tool_calls_made: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    rounds: int = 1
    max_rounds_hit: bool = False
