from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import Profile
from app.services.memory import MemoryService, count_tokens, truncate_to_token_budget
from app.services.memory_extractor import load_profile_context, retrieve_memories

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ContextResult:
    """Result of context assembly for an LLM interaction."""

    system_prompt: str
    profile_context: dict
    memories_used: int
    token_counts: dict  # {"profile": N, "memories": N, "total": N}


# ---------------------------------------------------------------------------
# Default template
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATE = """You are a knowledgeable health assistant.

## MEDICAL DISCLAIMER
You provide general health information, NOT medical diagnoses. Always recommend consulting
a healthcare professional for specific medical concerns.

{profile_section}

## Relevant History
{memories_section}

## INSTRUCTIONS
- Reference the patient's profile and history when relevant.
- Be accurate, concise, and evidence-based.
- If the question involves symptoms that could indicate a serious condition,
  recommend consulting a healthcare professional."""


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_allergy(allergy: dict) -> str:
    """Format a single allergy entry with severity and reaction details."""
    allergen = allergy.get("allergen", str(allergy))
    severity = allergy.get("severity", "")
    reaction = allergy.get("reaction", "")
    detail_parts: list[str] = []
    if severity:
        detail_parts.append(severity)
    if reaction:
        detail_parts.append(reaction)
    if detail_parts:
        return f"{allergen} ({' — '.join(detail_parts)})"
    return allergen


def _format_medication(med: dict) -> str:
    """Format a single medication entry with dosage and frequency."""
    name = med.get("name", str(med))
    dosage = med.get("dosage", "")
    frequency = med.get("frequency", "")
    result = name
    if dosage:
        result += f" {dosage}"
    if frequency:
        result += f", {frequency}"
    return result


def _format_condition(cond: dict) -> str:
    """Format a single medical condition with diagnosis date and status."""
    condition = cond.get("condition", str(cond))
    diagnosed = cond.get("diagnosed", "")
    status = cond.get("status", "")
    details: list[str] = []
    if diagnosed:
        details.append(f"diagnosed {diagnosed}")
    if status:
        details.append(status)
    if details:
        return f"{condition} ({', '.join(details)})"
    return condition


def format_profile_section(profile_context: dict) -> str:
    """Format profile data into a structured text block for LLM context.

    Takes the dict returned by ``load_profile_context`` (optionally enriched
    with a ``relationship`` key) and produces a multi-section markdown block.
    """
    name = profile_context.get("name", "Unknown")
    age = profile_context.get("age")
    sex = profile_context.get("sex") or "Not specified"
    blood_type = profile_context.get("blood_type")
    relationship = profile_context.get("relationship")

    # Header line
    header_parts = [
        f"Name: {name}",
        f"Age: {age}" if age is not None else "Age: Unknown",
        f"Sex: {sex}",
    ]
    lines: list[str] = ["## Patient Profile", " | ".join(header_parts)]
    if relationship:
        lines.append(f"Relationship to user: {relationship}")
    if blood_type:
        lines.append(f"Blood type: {blood_type}")

    # Allergies
    allergies: list[dict] = profile_context.get("allergies", [])
    lines += ["", "## Known Allergies"]
    if allergies:
        lines.extend(f"- {_format_allergy(a)}" for a in allergies)
    else:
        lines.append("None known")

    # Medications
    medications: list[dict] = profile_context.get("current_medications", [])
    lines += ["", "## Current Medications"]
    if medications:
        lines.extend(f"- {_format_medication(m)}" for m in medications)
    else:
        lines.append("None")

    # Conditions
    conditions: list[dict] = profile_context.get("medical_conditions", [])
    lines += ["", "## Medical Conditions"]
    if conditions:
        lines.extend(f"- {_format_condition(c)}" for c in conditions)
    else:
        lines.append("None known")

    # Family history
    family: dict[str, list[str]] = profile_context.get("family_medical_history", {})
    lines += ["", "## Family Medical History"]
    if family:
        for condition_name, members in family.items():
            lines.append(f"- {condition_name}: {', '.join(str(m) for m in members)}")
    else:
        lines.append("None reported")

    return "\n".join(lines)


def format_memories_section(memories: list[dict]) -> str:
    """Format episodic memories into a bullet list with optional timestamps.

    Memories are expected in relevance-sorted order (from Mem0 search).
    """
    if not memories:
        return "No relevant history found."

    lines: list[str] = []
    for mem in memories:
        text = mem.get("memory", "")
        timestamp = mem.get("updated_at") or mem.get("created_at") or ""
        date_prefix = _extract_date_prefix(timestamp)
        lines.append(f"- {date_prefix}{text}")

    return "\n".join(lines)


def _extract_date_prefix(timestamp: str | datetime | None) -> str:
    """Turn a timestamp into a ``[Mon YYYY] `` prefix, or empty string."""
    if not timestamp:
        return ""
    try:
        if isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        elif isinstance(timestamp, datetime):
            dt = timestamp
        else:
            return ""
        return f"[{dt.strftime('%b %Y')}] "
    except (ValueError, AttributeError):
        return ""


# ---------------------------------------------------------------------------
# ContextBuilder
# ---------------------------------------------------------------------------


class ContextBuilder:
    """Assembles context for LLM interactions.

    Loads profile data from PostgreSQL, retrieves relevant episodic memories
    from Mem0, formats both into a structured system prompt, and applies
    token budget constraints.
    """

    def __init__(self, memory_service: MemoryService) -> None:
        self._memory = memory_service

    async def build(
        self,
        db: AsyncSession,
        profile_id: UUID,
        query: str,
        interaction_type: str = "chat",
        *,
        memory_budget: int = 2000,
        template: str | None = None,
    ) -> ContextResult:
        """Build the full context for an LLM interaction.

        Args:
            db: Database session for loading profile.
            profile_id: The profile to build context for.
            query: User's current query (used for memory search).
            interaction_type: ``"diagnosis"``, ``"report_analysis"``, or ``"chat"``.
            memory_budget: Max tokens for the episodic memories section.
            template: Custom prompt template with ``{profile_section}`` and
                ``{memories_section}`` placeholders.

        Returns:
            ``ContextResult`` with the assembled system prompt and metadata.

        Raises:
            ValueError: If the profile does not exist.
        """
        # Fetch profile and memories sequentially. Memory retrieval is
        # best-effort — if Mem0 is unavailable we still return a useful
        # context built from the structured profile alone.
        # NOTE: we intentionally avoid asyncio.gather here because the db
        # session is not safe for concurrent coroutine use.
        profile = await db.get(Profile, profile_id)
        memories = await self._safe_retrieve_memories(profile_id, query, interaction_type)

        if profile is None:
            raise ValueError(f"Profile {profile_id} not found")

        # Build structured context
        profile_ctx = load_profile_context(profile)
        profile_ctx["relationship"] = profile.relationship

        profile_section = format_profile_section(profile_ctx)
        memories_section = format_memories_section(memories)

        # Token budget — profile always included, memories trimmed if over budget
        profile_tokens = count_tokens(profile_section)
        memories_tokens = count_tokens(memories_section)

        memories_injected = len(memories)
        if memories_tokens > memory_budget:
            memories_section = truncate_to_token_budget(memories_section, memory_budget)
            memories_tokens = count_tokens(memories_section)
            # Count surviving lines (each memory is a "- " prefixed line)
            memories_injected = sum(
                1 for line in memories_section.splitlines() if line.startswith("- ")
            )

        # Assemble final prompt
        prompt_template = template or DEFAULT_TEMPLATE
        system_prompt = prompt_template.format(
            profile_section=profile_section,
            memories_section=memories_section,
        )
        total_tokens = count_tokens(system_prompt)

        return ContextResult(
            system_prompt=system_prompt,
            profile_context=profile_ctx,
            memories_used=memories_injected,
            token_counts={
                "profile": profile_tokens,
                "memories": memories_tokens,
                "total": total_tokens,
            },
        )

    async def _safe_retrieve_memories(
        self,
        profile_id: UUID,
        query: str,
        interaction_type: str,
    ) -> list[dict]:
        """Retrieve memories with graceful degradation on failure."""
        try:
            return await retrieve_memories(self._memory, profile_id, query, interaction_type)
        except Exception:
            logger.warning(
                "Memory retrieval failed for profile %s, proceeding without memories",
                profile_id,
                exc_info=True,
            )
            return []
