"""Save-to-memory tool — lets the agent persist patient-stated health facts."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import UUID

from app.agents.types import ToolDefinition
from app.services.memory import MemoryService

logger = logging.getLogger(__name__)

# Valid categories (same as MemoryCategory in memory.py)
_VALID_CATEGORIES = {
    "medical_history",
    "medications",
    "allergies",
    "diagnoses",
    "symptoms",
    "lifestyle",
    "mental_health",
    "lab_results",
    "vitals",
    "procedures",
}


def build_save_memory_tool(
    memory_service: MemoryService,
    session_factory: Callable,
) -> ToolDefinition:
    """Create a ToolDefinition that saves patient-stated facts to long-term memory.

    Args:
        memory_service: For storing facts via ``add_raw(infer=False)``.
        session_factory: Async session factory for recording audit traces.
    """

    async def _handler(
        facts: list[dict[str, Any]],
        profile_id: str,
        source: str = "unknown",
    ) -> dict:
        try:
            pid = UUID(profile_id)
        except (ValueError, AttributeError):
            return {"error": f"Invalid profile_id: {profile_id}", "saved": 0}

        saved: list[dict] = []
        errors: list[str] = []
        mem0_results: list[dict] = []
        today = date.today().isoformat()

        for fact in facts:
            text = fact.get("text", "").strip() if isinstance(fact, dict) else str(fact).strip()
            if not text:
                continue

            category = fact.get("category", "general") if isinstance(fact, dict) else "general"
            if category not in _VALID_CATEGORIES:
                category = "general"

            try:
                result = await memory_service.add_raw(
                    pid,
                    text,
                    category=category,
                    source=source,
                )
                # Collect Mem0 results for audit trace
                for r in result.get("results", []):
                    mem0_results.append(r)
                saved.append({"text": text, "category": category, "date": today})
            except Exception as exc:
                logger.warning("Failed to save memory fact: %s", exc)
                errors.append(f"Failed to save: {text[:50]}")

        # Record audit trace (best-effort, own db session)
        if saved:
            try:
                from app.services.memory_trace import record_extraction

                async with session_factory() as trace_db:
                    await record_extraction(
                        trace_db,
                        profile_id=pid,
                        session_type=source.split(":")[0] if ":" in source else "chat",
                        session_id=_extract_session_id(source),
                        mem0_result={"results": mem0_results},
                        input_message_count=len(facts),
                    )
                    await trace_db.commit()
            except Exception:
                logger.warning("Failed to record memory trace for %s", source, exc_info=True)

        response: dict[str, Any] = {"saved": len(saved), "facts": saved}
        if errors:
            response["errors"] = errors
        return response

    return ToolDefinition(
        name="save_to_memory",
        description=(
            "Save important health facts the patient tells you to long-term memory. "
            "ONLY save facts the patient explicitly states. NEVER save: your own advice "
            "or recommendations, facts retrieved from memory search (already stored), "
            "facts already visible in the patient profile, "
            "speculative or hypothetical information, greetings or filler. "
            "DO save when the patient reports: medications (name, dosage, frequency), "
            "symptoms (type, duration, severity), diagnoses or test results, allergies, "
            "lifestyle changes, family medical history, surgeries or procedures. "
            "Each fact must be self-contained and specific — include dosages, dates, "
            "values, and units when mentioned."
        ),
        parameters={
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "A single, self-contained health fact",
                            },
                            "category": {
                                "type": "string",
                                "enum": sorted(_VALID_CATEGORIES),
                                "description": "Category for this fact",
                            },
                        },
                        "required": ["text", "category"],
                    },
                    "description": "List of health facts to save",
                },
            },
            "required": ["facts"],
        },
        handler=_handler,
    )


def _extract_session_id(source: str) -> UUID | None:
    """Extract a UUID from a source string like 'chat:uuid' or 'diagnosis:uuid:agent'."""
    parts = source.split(":")
    if len(parts) >= 2:
        try:
            return UUID(parts[1])
        except (ValueError, AttributeError):
            pass
    return None
