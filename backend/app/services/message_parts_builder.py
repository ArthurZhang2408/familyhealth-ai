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
    AssessmentAction,
    AssessmentCondition,
    AssessmentMedication,
    AssessmentPart,
    AssessmentSource,
    AssessmentTest,
    MemoryContextPart,
    MessagePart,
    StructuredInputPart,
    TextPart,
    ThinkingPart,
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
        self.thinking_text: str = ""

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
        elif event.type == AgentEventType.THINKING_DELTA:
            self.thinking_text += event.data.get("content", "")
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
    structured_response: dict[str, Any] | None = None,
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
    if structured_response:
        parts.append(
            StructuredInputPart(
                input_type=structured_response.get("input_type", ""),
                prompt=structured_response.get("prompt", ""),
                selected=structured_response.get("selected"),
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

    # Memory context — built from search_patient_memory tool results (agent-driven),
    # falling back to auto-injected context (for chat which still auto-retrieves).
    if accumulator:
        mem_results = [
            tr
            for tr in accumulator.tool_results
            if tr.name == "search_patient_memory" and not tr.is_error
        ]
        if mem_results:
            output = mem_results[0].output
            # Prefer memories_with_dates (has timestamps) over plain memories
            dated = output.get("memories_with_dates", [])
            if dated:
                memories = [{"text": m["text"], "date": m.get("date")} for m in dated]
            else:
                memories = [{"text": m, "date": None} for m in output.get("memories", [])]
            if memories:
                parts.append(MemoryContextPart(memories=memories, count=len(memories)))
    elif ctx and ctx.raw_memories:
        # Fallback for chat/reports which still use auto-retrieval
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

    # Thinking (from Gemini thinking mode) — after tools, before text
    if accumulator and accumulator.thinking_text:
        parts.append(ThinkingPart(text=accumulator.thinking_text))

    # Final text response — skip when assessment tool was called (assessment part replaces it)
    has_assessment = accumulator and any(
        tc.name == "present_assessment" for tc in accumulator.tool_calls
    )
    if not has_assessment:
        parts.append(TextPart(text=response_text))

    # Structured question from the last present_question tool call (if any)
    if accumulator:
        pq_calls = [tc for tc in accumulator.tool_calls if tc.name == "present_question"]
        if pq_calls:
            args = pq_calls[-1].arguments
            raw_options = args.get("options")
            raw_range = args.get("range")
            parts.append(
                StructuredInputPart(
                    input_type=args.get("input_type", "multiple_choice"),
                    prompt=args.get("prompt", ""),
                    options=raw_options if isinstance(raw_options, list) else None,
                    range=raw_range if isinstance(raw_range, dict) else None,
                )
            )

    # Structured assessment from the last present_assessment tool call (if any)
    if accumulator:
        pa_calls = [tc for tc in accumulator.tool_calls if tc.name == "present_assessment"]
        if pa_calls:
            parts.append(_build_assessment_part(pa_calls[-1].arguments))

    return serialize_parts(parts)


def _build_assessment_part(args: dict[str, Any]) -> AssessmentPart:
    """Build an AssessmentPart from present_assessment tool call arguments."""
    conditions = [
        AssessmentCondition(
            name=c.get("name", ""),
            confidence=c.get("confidence", "possible"),
            reasoning=c.get("reasoning", ""),
            confirming_tests=c.get("confirming_tests"),
        )
        for c in args.get("conditions", [])
    ]
    self_care = [
        AssessmentAction(action=s.get("action", ""), detail=s.get("detail"))
        for s in args.get("self_care", [])
    ]
    medications = [
        AssessmentMedication(
            name=m.get("name", ""),
            dosage=m.get("dosage", ""),
            notes=m.get("notes"),
        )
        for m in args.get("medications", [])
    ]
    tests = [
        AssessmentTest(
            name=t.get("name", ""),
            reason=t.get("reason", ""),
            urgency=t.get("urgency"),
        )
        for t in args.get("tests", [])
    ]
    sources = [
        AssessmentSource(title=s.get("title", ""), url=s.get("url", ""))
        for s in args.get("sources", [])
    ]
    return AssessmentPart(
        conditions=conditions,
        self_care=self_care,
        medications=medications,
        tests=tests,
        warnings=args.get("warnings", []),
        follow_up=args.get("follow_up"),
        sources=sources,
    )


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
            return dt.strftime("%b %-d, %Y")
        except (ValueError, AttributeError):
            pass
    return None
