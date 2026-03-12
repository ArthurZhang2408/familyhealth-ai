"""Service for recording LLM call traces (one row per provider call)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_trace import LLMTrace

logger = logging.getLogger(__name__)


def _sanitize_messages(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Strip image bytes from messages before storage."""
    if not messages:
        return messages
    sanitized = []
    for m in messages:
        entry: dict[str, Any] = {"role": m.get("role", ""), "content": m.get("content", "")}
        if m.get("image_parts"):
            entry["image_parts"] = [
                (
                    {"mime_type": ip.get("mime_type", "unknown"), "size": len(ip.get("data", b""))}
                    if isinstance(ip, dict)
                    else {
                        "mime_type": getattr(ip, "mime_type", "unknown"),
                        "size": len(getattr(ip, "data", b"")),
                    }
                )
                for ip in m["image_parts"]
            ]
        sanitized.append(entry)
    return sanitized


async def record_llm_traces(
    db: AsyncSession,
    *,
    session_type: str,
    session_id: UUID | None,
    turn_index: int | None,
    traces: list[dict[str, Any]],
) -> None:
    """Persist a batch of LLM call traces to the database.

    Best-effort: logs a warning on failure but never raises.
    """
    if not traces:
        return
    try:
        for t in traces:
            trace = LLMTrace(
                session_type=session_type,
                session_id=session_id,
                turn_index=turn_index,
                round_index=t.get("round_index"),
                provider=t.get("provider", "unknown"),
                model=t.get("model"),
                task=t.get("task", ""),
                system_prompt=t.get("system_prompt"),
                messages_in=_sanitize_messages(t.get("messages_in")),
                response_text=t.get("response_text"),
                response_tool_calls=t.get("response_tool_calls"),
                finish_reason=t.get("finish_reason"),
                tokens_in=t.get("tokens_in"),
                tokens_out=t.get("tokens_out"),
                latency_ms=t.get("latency_ms"),
                error=t.get("error"),
                is_fallback=t.get("is_fallback", False),
                fallback_reason=t.get("fallback_reason"),
            )
            db.add(trace)
        await db.flush()
    except Exception:
        logger.warning("Failed to record LLM traces", exc_info=True)
