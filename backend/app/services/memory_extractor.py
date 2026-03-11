from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from app.models.profile import Profile
from app.services.memory import MemoryService, truncate_to_token_budget

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chat system prompt template
# ---------------------------------------------------------------------------

CHAT_SYSTEM_PROMPT = """You are a friendly health assistant for {profile_name}.

## MEDICAL DISCLAIMER
You provide general health information, NOT medical diagnoses. Always recommend consulting
a healthcare professional for specific medical concerns.

## PATIENT PROFILE
- Age: {age} | Sex: {sex}
- Allergies: {allergies}
- Medications: {medications}
- Conditions: {conditions}

## RELEVANT CONTEXT
{episodic_memories}

## INSTRUCTIONS
- Answer health questions conversationally and accurately.
- Reference the patient's profile and history when relevant.
- If the question involves symptoms that could indicate a serious condition,
  recommend using the Diagnosis feature for a structured assessment.
- Be concise. Don't lecture unless asked for detail."""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def enrich_messages_with_date(messages: list[dict]) -> list[dict]:
    """Prepend a system message with today's date for temporal grounding."""
    date_context = {
        "role": "system",
        "content": f"Today's date is {date.today().isoformat()}.",
    }
    return [date_context] + messages


def load_profile_context(profile: Profile) -> dict:
    """Build a context dict from a Profile ORM object."""
    age = None
    if profile.date_of_birth:
        today = date.today()
        age = (
            today.year
            - profile.date_of_birth.year
            - ((today.month, today.day) < (profile.date_of_birth.month, profile.date_of_birth.day))
        )

    return {
        "name": profile.name,
        "sex": profile.sex,
        "age": age,
        "blood_type": profile.blood_type,
        "allergies": profile.allergies,
        "current_medications": profile.current_medications,
        "medical_conditions": profile.medical_conditions,
        "family_medical_history": profile.family_medical_history,
        "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg,
        "smoking_status": profile.smoking_status,
        "alcohol_frequency": profile.alcohol_frequency,
        "is_pregnant": profile.is_pregnant,
        "surgical_history": profile.surgical_history,
    }


def _format_list_field(items: list[dict], key: str) -> str:
    """Format a JSONB list field (allergies, medications, conditions) into a
    readable string. Returns ``'None known'`` if the list is empty.
    """
    if not items:
        return "None known"
    return ", ".join(item.get(key, str(item)) for item in items)


async def retrieve_memories(
    memory_service: MemoryService,
    profile_id: UUID,
    query: str,
    interaction_type: str,
) -> list[dict]:
    """Retrieve relevant episodic memories based on interaction type."""
    if interaction_type == "diagnosis":
        # Diagnosis retrieval: threshold 0.3 filters noise while keeping
        # relevant memories (Gemini embeddings rarely exceed 0.5 for short
        # medical phrases).  Limit 5 to avoid injecting marginal matches.
        return await memory_service.search(
            profile_id,
            query,
            limit=5,
            threshold=0.3,
        )
    elif interaction_type == "report_analysis":
        return await memory_service.search(
            profile_id,
            query,
            limit=10,
            categories=[
                "lab_results",
                "vitals",
                "medications",
                "medical_history",
            ],
            threshold=0.1,
        )
    else:  # chat
        return await memory_service.search(
            profile_id,
            query,
            limit=10,
            threshold=0.1,
        )


def assemble_system_prompt(
    template: str,
    profile_context: dict,
    episodic_memories: list[dict],
    token_budget: int,
) -> str:
    """Assemble a system prompt from template, profile context, and memories.

    Formats profile facts into template placeholders and applies a token budget
    to the episodic memories section.
    """
    # Format episodic memories as bullet lines
    memory_lines: list[str] = []
    for mem in episodic_memories:
        category = mem.get("metadata", {}).get("category", "general")
        text = mem.get("memory", "")
        memory_lines.append(f"- [{category}] {text}")

    memories_text = "\n".join(memory_lines) if memory_lines else "No prior context."
    memories_text = truncate_to_token_budget(memories_text, token_budget)

    return template.format(
        profile_name=profile_context.get("name", "Unknown"),
        age=profile_context.get("age") or "Unknown",
        sex=profile_context.get("sex") or "Unknown",
        allergies=_format_list_field(profile_context.get("allergies", []), "allergen"),
        medications=_format_list_field(profile_context.get("current_medications", []), "name"),
        conditions=_format_list_field(profile_context.get("medical_conditions", []), "condition"),
        episodic_memories=memories_text,
    )


# ---------------------------------------------------------------------------
# MemoryExtractor
# ---------------------------------------------------------------------------


class MemoryExtractor:
    """Orchestrates post-interaction memory extraction and storage."""

    def __init__(self, memory_service: MemoryService) -> None:
        self._memory = memory_service

    async def extract_and_store(
        self,
        profile_id: UUID,
        messages: list[dict],
        source: str,
        category: str | None = None,
    ) -> dict | None:
        """Run memory extraction via Mem0's internal LLM (infer=True)."""
        try:
            enriched = enrich_messages_with_date(messages)
            result = await self._memory.add(profile_id, enriched, category=category, source=source)
            logger.info("Memory extraction for profile %s completed", profile_id)
            return result
        except Exception:
            logger.exception("Memory extraction failed for profile %s", profile_id)
            return None

    async def store_narrative(
        self,
        profile_id: UUID,
        narrative: str,
        source: str,
        category: str = "diagnosis_summary",
    ) -> dict:
        """Store a single consolidated narrative — replaces any prior memories for this source.

        Uses delete-then-add (upsert) so follow-up assessments cleanly replace
        the previous narrative instead of accumulating duplicates.
        """
        deleted = 0
        try:
            deleted = await self._memory.delete_by_source(profile_id, source)
        except Exception:
            logger.warning("Failed to delete old memories for source %s", source)

        try:
            result = await self._memory.add_raw(
                profile_id,
                narrative,
                category=category,
                source=source,
            )
            results = result.get("results", [])
        except Exception:
            logger.warning(
                "Failed to store narrative for profile %s: %s", profile_id, narrative[:80]
            )
            results = []

        logger.info(
            "Stored narrative for profile %s (source=%s, deleted=%d prior)",
            profile_id,
            source,
            deleted,
        )
        return {"results": results, "deleted": deleted}
