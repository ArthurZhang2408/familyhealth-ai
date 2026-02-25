from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_memory_service, get_verified_profile
from app.core.database import get_db
from app.core.exceptions import AppError
from app.models.profile import Profile
from app.schemas.action_log import ActionType
from app.schemas.memory import MemoryFact, MemoryFactsResponse, MemorySummaryResponse
from app.services.action_log import ActionLogService
from app.services.memory import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles/{pid}/memory", tags=["memory"])


def _to_memory_fact(raw: dict) -> MemoryFact:
    """Convert a raw Mem0 memory dict to a MemoryFact schema."""
    metadata = raw.get("metadata", {})
    return MemoryFact(
        id=raw.get("id", ""),
        memory=raw.get("memory", ""),
        category=metadata.get("category"),
        source=metadata.get("source"),
        score=raw.get("score"),
        created_at=raw.get("created_at"),
        updated_at=raw.get("updated_at"),
    )


@router.get("")
async def get_memory_summary(
    profile: Profile = Depends(get_verified_profile),
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemorySummaryResponse:
    """Get memory summary for the profile."""
    memories = await memory_service.get_all(profile.id)
    facts = [_to_memory_fact(m) for m in memories]
    return MemorySummaryResponse(
        profile_id=str(profile.id),
        facts_count=len(facts),
        memories=facts,
    )


@router.get("/facts")
async def list_facts(
    profile: Profile = Depends(get_verified_profile),
    memory_service: MemoryService = Depends(get_memory_service),
    category: str | None = Query(None),
) -> MemoryFactsResponse:
    """List extracted episodic memory facts, optionally filtered by category."""
    memories = await memory_service.get_all(profile.id, category=category)
    return MemoryFactsResponse(
        profile_id=str(profile.id),
        facts=[_to_memory_fact(m) for m in memories],
    )


@router.delete("/{mid}", status_code=204)
async def delete_memory(
    mid: str,
    profile: Profile = Depends(get_verified_profile),
    memory_service: MemoryService = Depends(get_memory_service),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a specific memory entry."""
    try:
        await memory_service.delete(profile.id, mid)
    except ValueError:
        raise AppError(status_code=404, detail="Memory not found", code="NOT_FOUND")

    # Best-effort audit log
    try:
        log_svc = ActionLogService(db)
        await log_svc.log(
            profile.id,
            profile.account_id,
            ActionType.MEMORY_DELETED,
            {"memory_id": mid},
        )
        await db.commit()
    except Exception:
        logger.warning("Failed to log memory deletion for profile %s", profile.id, exc_info=True)
