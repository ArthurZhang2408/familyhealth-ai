"""Helper to build content_parts from streaming events and context data.

Used by ChatService and DiagnosisService to accumulate rich content parts
during agent execution and package them for message persistence.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.types import AgentEvent, AgentEventType, ToolCall, ToolResult
from app.schemas.message_parts import (
    AgentStepRecord,
    AgentStepsPart,
    MemoryContextPart,
    MessagePart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    serialize_parts,
)
from app.schemas.message_parts import (
    ImagePart as ImagePartSchema,
)
from app.services.context_builder import ContextResult
from app.services.llm import ImagePart as LLMImagePart
from app.services.storage import upload_chat_image

logger = logging.getLogger(__name__)


class PartsAccumulator:
    """Accumulates agent events into content parts during streaming."""

    def __init__(self) -> None:
        self.agent_steps: list[AgentStepRecord] = []
        self.tool_calls: list[ToolCallPart] = []
        self.tool_results: list[ToolResultPart] = []

    def record_event(self, event: AgentEvent) -> None:
        """Record an agent event for later persistence."""
        if event.type == AgentEventType.STATUS:
            self.agent_steps.append(
                AgentStepRecord(
                    id=event.data.get("step", ""),
                    message=event.data.get("message", ""),
                    tool=event.data.get("tool"),
                    details=event.data.get("details"),
                )
            )
        elif event.type == AgentEventType.TOOL_CALL:
            self.tool_calls.append(
                ToolCallPart(
                    id=event.data.get("id", f"tc_{event.data.get('tool', '')}"),
                    name=event.data.get("tool", ""),
                    arguments=event.data.get("arguments", {}),
                )
            )
        elif event.type == AgentEventType.TOOL_RESULT:
            self.tool_results.append(
                ToolResultPart(
                    call_id=event.data.get("call_id", ""),
                    name=event.data.get("tool", ""),
                    output=event.data.get("output", {}),
                    is_error=event.data.get("is_error", False),
                    summary=event.data.get("summary"),
                )
            )


def build_user_parts(
    content: str,
    image_urls: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Build content_parts for a user message."""
    parts: list[MessagePart] = [TextPart(text=content)]
    if image_urls:
        for img in image_urls:
            parts.append(
                ImagePartSchema(
                    url=img["url"],
                    mime_type=img["mime_type"],
                    filename=img.get("filename"),
                )
            )
    return serialize_parts(parts)


def build_assistant_parts(
    response_text: str,
    accumulator: PartsAccumulator | None = None,
    ctx: ContextResult | None = None,
) -> list[dict[str, Any]]:
    """Build content_parts for an assistant message."""
    parts: list[MessagePart] = []

    # Agent steps (context loading, memory retrieval, etc.)
    if accumulator and accumulator.agent_steps:
        parts.append(AgentStepsPart(steps=accumulator.agent_steps))

    # Memory context
    if ctx and ctx.raw_memories:
        memories = []
        for mem in ctx.raw_memories[:5]:
            memories.append(
                {
                    "text": mem.get("memory", ""),
                    "date": _extract_date(mem),
                }
            )
        parts.append(MemoryContextPart(memories=memories, count=ctx.memories_used))

    # Tool calls and results (interleaved in order)
    if accumulator:
        for tc in accumulator.tool_calls:
            parts.append(tc)
        for tr in accumulator.tool_results:
            parts.append(tr)

    # Final text response
    parts.append(TextPart(text=response_text))

    return serialize_parts(parts)


def build_assistant_parts_from_result(
    response_text: str,
    tool_calls: list[ToolCall] | None = None,
    tool_results: list[ToolResult] | None = None,
    ctx: ContextResult | None = None,
) -> list[dict[str, Any]]:
    """Build content_parts for a non-streaming assistant message (from AgentResult)."""
    parts: list[MessagePart] = []

    # Memory context
    if ctx and ctx.raw_memories:
        memories = []
        for mem in ctx.raw_memories[:5]:
            memories.append(
                {
                    "text": mem.get("memory", ""),
                    "date": _extract_date(mem),
                }
            )
        parts.append(MemoryContextPart(memories=memories, count=ctx.memories_used))

    # Tool calls and results
    if tool_calls:
        for tc in tool_calls:
            parts.append(ToolCallPart(id=tc.id, name=tc.name, arguments=tc.arguments))
    if tool_results:
        for tr in tool_results:
            parts.append(
                ToolResultPart(
                    call_id=tr.call_id,
                    name=tr.name,
                    output=tr.output,
                    is_error=tr.is_error,
                )
            )

    # Final text response
    parts.append(TextPart(text=response_text))

    return serialize_parts(parts)


async def upload_images_for_parts(
    image_parts: list[LLMImagePart],
    profile_id: Any,
) -> list[dict[str, str]]:
    """Upload image bytes to Supabase Storage and return URL metadata for content_parts."""
    results = []
    for img in image_parts:
        try:
            url = await upload_chat_image(img.data, img.mime_type, profile_id)
            results.append({"url": url, "mime_type": img.mime_type})
        except Exception:
            logger.warning("Failed to upload chat image, skipping persistence", exc_info=True)
    return results


def _extract_date(mem: dict) -> str | None:
    ts = mem.get("updated_at") or mem.get("created_at") or ""
    if ts:
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            return dt.strftime("%b %Y")
        except (ValueError, AttributeError):
            pass
    return None
