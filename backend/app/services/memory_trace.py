"""Service for recording memory system traces (retrieval + extraction)."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_trace import MemoryTrace

logger = logging.getLogger(__name__)


async def record_retrieval(
    db: AsyncSession,
    *,
    profile_id: UUID,
    session_type: str,
    session_id: UUID | None,
    turn_number: int | None,
    query: str,
    raw_memories: list[dict],
    injected_count: int,
) -> None:
    """Record a memory retrieval event (what was fetched before an agent turn)."""
    try:
        results = [
            {
                "id": str(m.get("id", "")),
                "memory": m.get("memory", ""),
                "score": round(m.get("score", 0), 4),
            }
            for m in raw_memories
        ]
        trace = MemoryTrace(
            profile_id=profile_id,
            session_type=session_type,
            session_id=session_id,
            event_type="retrieval",
            turn_number=turn_number,
            payload={
                "query": query,
                "results": results,
                "retrieved_count": len(results),
                "injected_count": injected_count,
            },
        )
        db.add(trace)
        await db.flush()
    except Exception:
        logger.warning("Failed to record retrieval trace", exc_info=True)


async def record_extraction(
    db: AsyncSession,
    *,
    profile_id: UUID,
    session_type: str,
    session_id: UUID | None,
    mem0_result: dict | None,
    input_message_count: int,
) -> None:
    """Record a memory extraction event (what was stored after a session)."""
    try:
        # Mem0 returns {"results": [{"id": ..., "memory": ..., "event": "ADD|UPDATE|..."}]}
        results = []
        if mem0_result and "results" in mem0_result:
            for r in mem0_result["results"]:
                results.append(
                    {
                        "id": str(r.get("id", "")),
                        "memory": r.get("memory", ""),
                        "event": r.get("event", ""),
                    }
                )

        trace = MemoryTrace(
            profile_id=profile_id,
            session_type=session_type,
            session_id=session_id,
            event_type="extraction",
            payload={
                "input_message_count": input_message_count,
                "results": results,
                "facts_stored": len([r for r in results if r["event"] in ("ADD", "UPDATE")]),
            },
        )
        db.add(trace)
        await db.flush()
    except Exception:
        logger.warning("Failed to record extraction trace", exc_info=True)
