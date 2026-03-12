"""Debug endpoints for inspecting session traces and receiving client logs.

Dev-only — guarded by app_env == "development".
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_account
from app.models.chat import ChatMessage
from app.models.diagnosis import DiagnosisMessage
from app.models.llm_trace import LLMTrace
from app.models.memory_trace import MemoryTrace

logger = logging.getLogger(__name__)
_client_logger = logging.getLogger("client")

router = APIRouter(prefix="/debug", tags=["debug"])


def _require_dev() -> None:
    if settings.app_env != "development":
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/sessions/{session_id}")
async def get_session_debug(
    session_id: UUID,
    session_type: str = Query(..., pattern="^(chat|diagnosis)$"),
    _account=Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Unified timeline of messages, LLM traces, and memory traces for a session."""
    _require_dev()

    timeline: list[dict] = []

    # Messages
    if session_type == "chat":
        msg_q = (
            select(ChatMessage)
            .where(ChatMessage.conversation_id == session_id)
            .order_by(ChatMessage.created_at)
        )
    else:
        msg_q = (
            select(DiagnosisMessage)
            .where(DiagnosisMessage.session_id == session_id)
            .order_by(DiagnosisMessage.created_at)
        )

    messages = (await db.execute(msg_q)).scalars().all()
    for msg in messages:
        timeline.append(
            {
                "kind": "message",
                "created_at": msg.created_at.isoformat(),
                "id": str(msg.id),
                "role": msg.role,
                "content": msg.content,
                "content_parts": msg.content_parts,
                "metadata": msg.metadata_,
            }
        )

    # LLM traces
    llm_q = (
        select(LLMTrace)
        .where(
            LLMTrace.session_id == session_id,
            LLMTrace.session_type == session_type,
        )
        .order_by(LLMTrace.created_at)
    )
    llm_traces = (await db.execute(llm_q)).scalars().all()
    for t in llm_traces:
        timeline.append(
            {
                "kind": "llm_trace",
                "created_at": t.created_at.isoformat(),
                "id": t.id,
                "turn_index": t.turn_index,
                "round_index": t.round_index,
                "provider": t.provider,
                "model": t.model,
                "task": t.task,
                "system_prompt": t.system_prompt,
                "messages_in": t.messages_in,
                "response_text": t.response_text,
                "response_tool_calls": t.response_tool_calls,
                "finish_reason": t.finish_reason,
                "tokens_in": t.tokens_in,
                "tokens_out": t.tokens_out,
                "latency_ms": t.latency_ms,
                "error": t.error,
                "is_fallback": t.is_fallback,
                "fallback_reason": t.fallback_reason,
            }
        )

    # Memory traces
    mem_q = (
        select(MemoryTrace)
        .where(
            MemoryTrace.session_id == session_id,
        )
        .order_by(MemoryTrace.created_at)
    )
    mem_traces = (await db.execute(mem_q)).scalars().all()
    for mt in mem_traces:
        timeline.append(
            {
                "kind": "memory_trace",
                "created_at": mt.created_at.isoformat(),
                "id": mt.id,
                "event_type": mt.event_type,
                "turn_number": mt.turn_number,
                "payload": mt.payload,
            }
        )

    # Sort by created_at
    timeline.sort(key=lambda e: e["created_at"])

    return {
        "session_id": str(session_id),
        "session_type": session_type,
        "event_count": len(timeline),
        "timeline": timeline,
    }


@router.get("/sessions/{session_id}/traces")
async def get_session_traces(
    session_id: UUID,
    session_type: str = Query("diagnosis", pattern="^(chat|diagnosis|report|standalone)$"),
    _account=Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """LLM traces only for a session — lighter than full timeline."""
    _require_dev()

    q = (
        select(LLMTrace)
        .where(
            LLMTrace.session_id == session_id,
            LLMTrace.session_type == session_type,
        )
        .order_by(LLMTrace.created_at)
    )
    traces = (await db.execute(q)).scalars().all()

    return {
        "session_id": str(session_id),
        "trace_count": len(traces),
        "traces": [
            {
                "id": t.id,
                "turn_index": t.turn_index,
                "round_index": t.round_index,
                "provider": t.provider,
                "model": t.model,
                "task": t.task,
                "system_prompt_length": len(t.system_prompt) if t.system_prompt else 0,
                "messages_in_count": len(t.messages_in) if t.messages_in else 0,
                "response_text_preview": t.response_text[:300] if t.response_text else None,
                "response_tool_calls": t.response_tool_calls,
                "finish_reason": t.finish_reason,
                "tokens_in": t.tokens_in,
                "tokens_out": t.tokens_out,
                "latency_ms": t.latency_ms,
                "error": t.error,
                "is_fallback": t.is_fallback,
                "fallback_reason": t.fallback_reason,
                "created_at": t.created_at.isoformat(),
            }
            for t in traces
        ],
    }


@router.post("/client-logs")
async def receive_client_logs(
    entries: list[dict[str, Any]] = Body(..., max_length=100),
    _account=Depends(get_current_account),
) -> dict:
    """Receive and persist client-side log entries.

    Written to the server log file under the 'client' logger so they
    appear alongside server-side logs and can be correlated by timestamp
    and request ID (rid).
    """
    _require_dev()

    for entry in entries[:100]:
        level = str(entry.get("level", "info"))[:10]
        category = str(entry.get("category", "app"))[:20]
        message = str(entry.get("message", ""))[:500]
        data = entry.get("data")
        ts = str(entry.get("timestamp", ""))[:30]
        rid = data.get("rid") if isinstance(data, dict) else None

        log_line = f"[{ts}] [{category}] {message}"
        if data:
            log_line += f" {str(data)[:500]}"

        log_fn = {
            "error": _client_logger.error,
            "warn": _client_logger.warning,
            "debug": _client_logger.debug,
        }.get(level, _client_logger.info)
        log_fn("MOBILE %s", log_line, extra={"request_id": rid or "-"})

    return {"received": len(entries)}
