"""Profile lookup tool — loads structured patient profile for agent use."""

from __future__ import annotations

from uuid import UUID

from app.agents.types import ToolDefinition
from app.services.memory_extractor import load_profile_context


def build_profile_lookup_tool(db_session_factory) -> ToolDefinition:
    """Create a ToolDefinition that loads a patient's structured profile."""

    async def _handler(profile_id: str, **_kwargs: object) -> dict:
        from app.models.profile import Profile

        try:
            pid = UUID(profile_id)
        except (ValueError, AttributeError):
            return {"error": f"Invalid profile_id: {profile_id}"}
        async with db_session_factory() as db:
            profile = await db.get(Profile, pid)
            if not profile:
                return {"error": "Profile not found"}
            ctx = load_profile_context(profile)
            ctx["relationship"] = profile.relationship
            return ctx

    return ToolDefinition(
        name="get_profile_context",
        description=(
            "Get the patient's structured profile data including demographics, "
            "allergies, current medications, medical conditions, and family "
            "medical history."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
        handler=_handler,
    )
