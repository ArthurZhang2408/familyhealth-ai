from __future__ import annotations

import asyncio
import logging
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

import tiktoken
from mem0 import Memory

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MemoryCategory
# ---------------------------------------------------------------------------


class MemoryCategory(StrEnum):
    MEDICAL_HISTORY = "medical_history"
    MEDICATIONS = "medications"
    ALLERGIES = "allergies"
    DIAGNOSES = "diagnoses"
    SYMPTOMS = "symptoms"
    LIFESTYLE = "lifestyle"
    MENTAL_HEALTH = "mental_health"
    LAB_RESULTS = "lab_results"
    VITALS = "vitals"
    PROCEDURES = "procedures"


# ---------------------------------------------------------------------------
# Mem0 config builder
# ---------------------------------------------------------------------------


def build_mem0_config(settings: Settings) -> dict:
    """Build the full Mem0 configuration dict from application settings.

    Note: The ``llm`` block is required by Mem0 at init time, but never
    actually invoked — all saves use ``infer=False``.  We point it at Gemini
    so it doesn't need a separate API key.
    """
    return {
        "version": "v1.1",
        "llm": {
            "provider": "gemini",
            "config": {
                "model": settings.gemini_flash_model,
                "api_key": settings.gemini_api_key,
                "temperature": 0.1,
                "max_tokens": 2000,
            },
        },
        "embedder": {
            "provider": "gemini",
            "config": {
                "model": settings.embedding_model,
                "api_key": settings.gemini_api_key,
                "embedding_dims": settings.embedding_dims,
            },
        },
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "dbname": settings.pg_mem0_database,
                "collection_name": "health_memories",
                "embedding_model_dims": settings.embedding_dims,
                "host": settings.pg_host,
                "port": settings.pg_port,
                "user": settings.pg_user,
                "password": settings.pg_password,
                "hnsw": True,
                "minconn": 2,
                "maxconn": 10,
            },
        },
    }


# ---------------------------------------------------------------------------
# Token utilities
# ---------------------------------------------------------------------------

_encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count the number of tokens in a text string."""
    return len(_encoder.encode(text))


def truncate_to_token_budget(text: str, max_tokens: int) -> str:
    """Truncate text to fit within a token budget, preserving complete lines."""
    tokens = _encoder.encode(text)
    if len(tokens) <= max_tokens:
        return text
    truncated = _encoder.decode(tokens[:max_tokens])
    last_newline = truncated.rfind("\n")
    if last_newline > 0:
        truncated = truncated[:last_newline]
    return truncated + "\n- [... additional history truncated for context limit]"


def build_conversation_window(messages: list[dict], max_tokens: int) -> list[dict]:
    """Select most recent messages fitting the token budget.

    Always includes the first message (typically the system prompt).
    """
    if not messages:
        return []

    first_msg = messages[0]
    first_tokens = count_tokens(first_msg["content"])
    if first_tokens >= max_tokens:
        return [first_msg]
    remaining_budget = max_tokens - first_tokens

    selected: list[dict] = []
    for msg in reversed(messages[1:]):
        msg_tokens = count_tokens(msg["content"])
        if msg_tokens > remaining_budget:
            break
        selected.insert(0, msg)
        remaining_budget -= msg_tokens

    return [first_msg] + selected


# ---------------------------------------------------------------------------
# MemoryService
# ---------------------------------------------------------------------------


class MemoryService:
    """Thin async wrapper around the Mem0 Memory client.

    All blocking Mem0 calls are dispatched to a thread via ``asyncio.to_thread``
    so they don't block the event loop.
    """

    def __init__(self, mem0_client: Memory) -> None:
        self._mem0 = mem0_client

    async def add(
        self,
        profile_id: UUID,
        messages: str | list[dict],
        *,
        category: str | None = None,
        source: str = "conversation",
    ) -> dict:
        """Add memories extracted from messages for a given profile."""
        metadata: dict[str, str] = {"source": source}
        if category:
            metadata["category"] = category
        return await asyncio.to_thread(
            self._mem0.add,
            messages,
            user_id=str(profile_id),
            metadata=metadata,
        )

    async def add_raw(
        self,
        profile_id: UUID,
        fact: str,
        *,
        category: str | None = None,
        source: str = "conversation",
    ) -> dict:
        """Store a pre-extracted fact directly — bypasses Mem0's internal LLM.

        Uses ``infer=False`` so Mem0 only embeds and stores; no nemotron
        extraction or dedup logic runs.
        """
        metadata: dict[str, str] = {"source": source}
        if category:
            metadata["category"] = category
        return await asyncio.to_thread(
            self._mem0.add,
            fact,
            user_id=str(profile_id),
            metadata=metadata,
            infer=False,
        )

    async def search(
        self,
        profile_id: UUID,
        query: str,
        *,
        limit: int = 10,
        categories: list[str] | None = None,
        threshold: float = 0.1,
    ) -> list[dict]:
        """Search memories by semantic similarity."""
        # Mem0's pgvector backend only supports exact equality filters
        # (payload->>key = value), not operator-style ({"in": [...]}).
        # For multiple categories, run separate searches and merge.
        if categories and len(categories) == 1:
            filters = {"category": categories[0]}
            result = await asyncio.to_thread(
                self._mem0.search,
                query,
                user_id=str(profile_id),
                limit=limit,
                filters=filters,
                threshold=threshold,
            )
            return result.get("results", [])
        elif categories:
            # Multiple categories: search each and merge by score
            all_results: dict[str, dict] = {}
            for cat in categories:
                result = await asyncio.to_thread(
                    self._mem0.search,
                    query,
                    user_id=str(profile_id),
                    limit=limit,
                    filters={"category": cat},
                    threshold=threshold,
                )
                for r in result.get("results", []):
                    rid = r.get("id", "")
                    existing_score = all_results.get(rid, {}).get("score", 999)
                    if rid not in all_results or r.get("score", 0) < existing_score:
                        all_results[rid] = r
            # Sort by score (lower = more similar in Mem0's distance metric)
            merged = sorted(all_results.values(), key=lambda r: r.get("score", 999))
            return merged[:limit]
        else:
            result = await asyncio.to_thread(
                self._mem0.search,
                query,
                user_id=str(profile_id),
                limit=limit,
                threshold=threshold,
            )
            return result.get("results", [])

    async def get_all(
        self,
        profile_id: UUID,
        *,
        category: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Retrieve all memories for a profile, optionally filtered by category."""
        filters = {"category": category} if category else None
        result = await asyncio.to_thread(
            self._mem0.get_all,
            user_id=str(profile_id),
            filters=filters,
            limit=limit,
        )
        return result.get("results", [])

    async def get_history(self, memory_id: str) -> list[dict]:
        """Get the edit history of a specific memory."""
        return await asyncio.to_thread(self._mem0.history, memory_id)

    async def delete(self, profile_id: UUID, memory_id: str) -> None:
        """Delete a single memory, ensuring it belongs to the given profile."""
        mem = await asyncio.to_thread(self._mem0.get, memory_id)
        if not mem or mem.get("user_id") != str(profile_id):
            raise ValueError("Memory does not belong to this profile")
        await asyncio.to_thread(self._mem0.delete, memory_id)

    async def delete_all(self, profile_id: UUID) -> None:
        """Delete all memories for a profile."""
        await asyncio.to_thread(self._mem0.delete_all, user_id=str(profile_id))

    async def delete_by_source(self, profile_id: UUID, source: str) -> int:
        """Delete all memories for a profile that were extracted from a specific source.

        Args:
            profile_id: The profile whose memories to search.
            source: The source tag, e.g. ``"diagnosis:uuid"`` or ``"chat:uuid"``.

        Returns:
            Number of memories deleted.
        """
        result = await asyncio.to_thread(
            self._mem0.get_all,
            user_id=str(profile_id),
            filters={"source": source},
            limit=1000,
        )
        memories = result.get("results", [])
        # Guard: verify each memory actually has the expected source before
        # deleting. If Mem0 silently ignores the filter, we'd otherwise
        # delete ALL memories for the profile.
        deleted = 0
        for mem in memories:
            if mem.get("metadata", {}).get("source") != source:
                continue
            await asyncio.to_thread(self._mem0.delete, mem["id"])
            deleted += 1
        return deleted

