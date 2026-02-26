"""Per-interaction agent session state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.agents.types import ToolCall, ToolResult


@dataclass
class AgentSession:
    """Ephemeral state for a single AgentCore.run() invocation.

    Not a DB entity — lives only for the duration of one agentic interaction.
    The calling service is responsible for persisting relevant outputs.
    """

    profile_id: UUID
    system_prompt: str
    messages: list[dict[str, Any]]
    tool_calls_made: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    turn_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
