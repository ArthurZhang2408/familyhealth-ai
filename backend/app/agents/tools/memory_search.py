"""Memory search tool — wraps MemoryService.search() for agent use."""

from __future__ import annotations

from uuid import UUID

from app.agents.types import ToolDefinition
from app.services.memory import MemoryService


def build_memory_search_tool(memory_service: MemoryService) -> ToolDefinition:
    """Create a ToolDefinition that searches patient episodic memory."""

    async def _handler(
        query: str,
        profile_id: str,
        categories: list[str] | None = None,
        limit: int = 10,
        **_kwargs: object,
    ) -> dict:
        try:
            pid = UUID(profile_id)
        except (ValueError, AttributeError):
            return {"error": f"Invalid profile_id: {profile_id}", "memories": [], "count": 0}
        results = await memory_service.search(
            pid,
            query,
            limit=limit,
            categories=categories,
            threshold=0.05,
        )
        memories = []
        memories_with_dates = []
        for m in results:
            text = m.get("memory", "")
            if not text:
                continue
            # Extract date for both LLM context and UI display
            ts = m.get("updated_at") or m.get("created_at") or ""
            date_str = None
            if ts:
                try:
                    from datetime import datetime

                    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    date_str = dt.strftime("%b %-d, %Y")
                except (ValueError, AttributeError):
                    pass
            # Include date in the string the LLM sees — temporal context matters
            if date_str:
                memories.append(f"[{date_str}] {text}")
            else:
                memories.append(text)
            memories_with_dates.append({"text": text, "date": date_str})
        return {
            "memories": memories,  # date-prefixed strings for the LLM
            "memories_with_dates": memories_with_dates,  # structured for UI
            "count": len(memories),
            "query": query,  # persisted for debug / UI display
        }

    return ToolDefinition(
        name="search_patient_memory",
        description=(
            "Search the patient's stored health memories by semantic similarity. "
            "Use this to find previous lab results, diagnoses, symptoms, "
            "medications, or any prior health interactions. Returns a list "
            "of relevant memory entries."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Semantic search query describing what to find",
                },
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional category filter: lab_results, vitals, "
                        "medications, diagnoses, medical_history"
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 10)",
                },
            },
            "required": ["query"],
        },
        handler=_handler,
    )
