from __future__ import annotations

from pydantic import BaseModel


class MemoryFact(BaseModel):
    id: str
    memory: str
    category: str | None = None
    source: str | None = None
    score: float | None = None
    created_at: str | None = None
    updated_at: str | None = None


class MemorySummaryResponse(BaseModel):
    profile_id: str
    facts_count: int
    memories: list[MemoryFact]


class MemoryFactsResponse(BaseModel):
    profile_id: str
    facts: list[MemoryFact]
