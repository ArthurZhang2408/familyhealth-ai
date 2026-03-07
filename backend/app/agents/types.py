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
    terminal: bool = False  # If True, stops the agent loop after execution

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
    STATUS = "status"
    TEXT_DELTA = "text_delta"
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    COMPLETE = "complete"
    DONE = "done"
    STRUCTURED_QUESTION = "structured_question"


@dataclass
class AgentEvent:
    """An event emitted during agent execution (for observability / streaming)."""

    type: AgentEventType
    data: dict[str, Any] = field(default_factory=dict)


class AgentDefinition:
    """Configuration for a specific agent type.

    Specifies which LLM task to use, which tools are available,
    and generation parameters.
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        task: str,
        tool_names: list[str] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4000,
        max_tool_rounds: int = 5,
        response_format: dict | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.task = task
        self.tool_names = tool_names or []
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_tool_rounds = max_tool_rounds
        self.response_format = response_format


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
