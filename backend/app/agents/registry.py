"""Centralized tool registration and execution."""

from __future__ import annotations

import logging
from typing import Any

from app.agents.types import ToolCall, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registers tools at startup and executes them on behalf of agents."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool
        logger.info("Tool registered: %s", tool.name)

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def get_declarations(self, names: list[str]) -> list[dict[str, Any]] | None:
        """Return JSON Schema declarations for the given tool names.

        Returns None if no valid tools are found (so LLMRequest.tools=None
        disables tool calling entirely).
        """
        decls = []
        for n in names:
            tool = self._tools.get(n)
            if tool:
                decls.append(tool.to_declaration())
        return decls or None

    async def execute(
        self,
        call: ToolCall,
        *,
        injected_args: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Execute a tool call, merging any injected arguments.

        ``injected_args`` are added to the call arguments before dispatch.
        This allows the AgentCore to inject context like ``profile_id``
        without the LLM needing to know it.
        """
        tool = self._tools.get(call.name)
        if not tool:
            return ToolResult(
                call_id=call.id,
                name=call.name,
                output={"error": f"Unknown tool: {call.name}"},
                is_error=True,
            )

        merged_args = {**(injected_args or {}), **call.arguments}

        try:
            output = await tool.handler(**merged_args)
            return ToolResult(call_id=call.id, name=call.name, output=output)
        except Exception as exc:
            logger.exception("Tool '%s' execution failed", call.name)
            return ToolResult(
                call_id=call.id,
                name=call.name,
                output={"error": str(exc)},
                is_error=True,
            )
