from __future__ import annotations

import asyncio
import json
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
# Prompts
# ---------------------------------------------------------------------------

FACT_EXTRACTION_PROMPT = """You are a medical information extraction system. Your job is to
extract discrete, factual health information from a conversation between a user and a health
assistant.

Extract ONLY concrete health facts. Each fact should be:
- Self-contained (understandable without the conversation context)
- Specific (include dosages, dates, values, severity when mentioned)
- Attributed with temporal status (current vs. historical)
- One fact per item (don't combine multiple facts)

CATEGORIES to tag each fact with:
- medical_history: past diagnoses, surgeries, hospitalizations
- medications: current and past medications with dosage/frequency
- allergies: drug allergies, food allergies, environmental allergies
- diagnoses: new diagnoses from this or recent interactions
- symptoms: reported symptoms with duration, frequency, severity
- lifestyle: diet, exercise, sleep, smoking, alcohol
- mental_health: mood, stress, anxiety, sleep issues
- lab_results: test values with units, reference ranges, dates
- vitals: blood pressure, heart rate, weight, temperature
- procedures: surgeries, treatments, therapies

DO extract:
- "Started metformin 500mg twice daily in January 2026"
- "Blood pressure measured at 140/90 on 2026-02-15"
- "Allergic to penicillin — causes hives and throat swelling"
- "Father had heart attack at age 55"
- "Reports morning headaches for the past 2 weeks, severity 6/10"

DO NOT extract:
- Greetings, pleasantries, or conversational filler
- The AI's reasoning or diagnostic process
- Questions the AI asked (only extract the user's answers)
- Speculative statements ("might be", "could indicate")
- Generic health advice given by the AI

Input conversation:
{input}

Return a JSON object:
{{"facts": ["fact 1", "fact 2", ...]}}

If no extractable health facts exist, return: {{"facts": []}}"""

UPDATE_MEMORY_PROMPT = """You are a medical memory management system. You must decide how to
handle a new health fact relative to existing stored memories.

EXISTING MEMORIES:
{existing_memories}

NEW FACT:
{memory}

For the new fact, decide ONE action:

- "ADD": The fact is genuinely new information not covered by any existing memory.
- "UPDATE": The fact updates, corrects, or supersedes an existing memory. Return the
  updated_memory_id of the memory being replaced, and provide the merged/updated text.
  IMPORTANT: When a medication, condition, or status changes, the UPDATE should reflect
  the CURRENT state. Preserve the historical context by noting what changed.
  Example: Old="Takes metformin 500mg 2x daily" + New="Increased metformin to 1000mg"
  → Updated="Takes metformin 1000mg 2x daily (increased from 500mg)"
- "DELETE": The fact explicitly negates an existing memory (e.g., "No longer allergic to X"
  after allergy desensitization). Return the memory_id to delete.
- "NONE": The fact is already fully captured by an existing memory (exact duplicate or
  semantically identical). No action needed.

TEMPORAL RULES:
- A fact about a CURRENT state ("is taking", "currently has") should UPDATE any
  contradicting fact about the same subject.
- A fact about a PAST state ("was taking", "used to have") should be ADDED as new
  historical context, NOT used to update a current-state memory.
- If unclear whether current or historical, default to ADD.

Return JSON:
{{"type": "ADD" | "UPDATE" | "DELETE" | "NONE",
  "updated_memory_id": "..." | null,
  "memory": "updated text" | null}}"""

REPORT_EXTRACTION_PROMPT = """You are extracting structured health facts from a medical
report analysis. The input is a JSON analysis of a lab report, blood test, or medical image.

Extract each finding as a standalone fact including:
- The measurement name and value with units
- Whether the value is normal, elevated, low, or critical
- The reference range if available
- The date of the test if available

Format each fact for long-term storage — it should be understandable months from now
without the original report.

Input:
{input}

Return: {{"facts": ["fact 1", "fact 2", ...]}}"""


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
    """Build the full Mem0 configuration dict from application settings."""
    return {
        "version": "v1.1",
        "llm": {
            "provider": "openai",
            "config": {
                "model": settings.qwen_model,
                "api_key": settings.qwen_api_key,
                "openai_base_url": settings.qwen_base_url,
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
        "custom_fact_extraction_prompt": FACT_EXTRACTION_PROMPT,
        "custom_update_memory_prompt": UPDATE_MEMORY_PROMPT,
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

    async def search(
        self,
        profile_id: UUID,
        query: str,
        *,
        limit: int = 10,
        categories: list[str] | None = None,
        threshold: float = 0.5,
    ) -> list[dict]:
        """Search memories by semantic similarity."""
        filters = None
        if categories:
            filters = {"category": {"in": categories}}
        result = await asyncio.to_thread(
            self._mem0.search,
            query,
            user_id=str(profile_id),
            limit=limit,
            filters=filters,
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
        if mem.get("user_id") != str(profile_id):
            raise ValueError("Memory does not belong to this profile")
        await asyncio.to_thread(self._mem0.delete, memory_id)

    async def delete_all(self, profile_id: UUID) -> None:
        """Delete all memories for a profile."""
        await asyncio.to_thread(self._mem0.delete_all, user_id=str(profile_id))

    async def extract_from_diagnosis(
        self, profile_id: UUID, messages: list[dict], session_id: str
    ) -> dict:
        """Extract and store memories from a diagnosis session."""
        return await self.add(
            profile_id,
            messages,
            category="diagnoses",
            source=f"diagnosis:{session_id}",
        )

    async def extract_from_report(self, profile_id: UUID, analysis: dict, report_id: str) -> dict:
        """Extract and store memories from a medical report analysis."""
        content = self._format_report_for_extraction(analysis)
        return await asyncio.to_thread(
            self._mem0.add,
            content,
            user_id=str(profile_id),
            metadata={
                "category": "lab_results",
                "source": f"report:{report_id}",
            },
            prompt=REPORT_EXTRACTION_PROMPT,
        )

    async def extract_from_chat(self, profile_id: UUID, messages: list[dict]) -> dict:
        """Extract and store memories from a chat conversation."""
        return await self.add(profile_id, messages, source="chat")

    @staticmethod
    def _format_report_for_extraction(analysis: dict) -> str:
        return json.dumps(analysis, indent=2, default=str)
