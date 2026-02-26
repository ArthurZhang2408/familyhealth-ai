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
        memories = [m.get("memory", "") for m in results if m.get("memory")]
        return {"memories": memories, "count": len(memories)}

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
