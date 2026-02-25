from fastapi import APIRouter, Depends

from app.api.deps import get_verified_profile
from app.models.profile import Profile

router = APIRouter(prefix="/profiles/{pid}/memory", tags=["memory"])


@router.get("")
async def get_memory_summary(
    profile: Profile = Depends(get_verified_profile),
) -> dict:
    """Get memory summary for the profile. Mem0 integration will be added in a future release."""
    return {"profile_id": str(profile.id), "facts_count": 0, "memories": []}


@router.get("/facts")
async def list_facts(
    profile: Profile = Depends(get_verified_profile),
) -> dict:
    """List extracted episodic memory facts. Mem0 integration will be added in a future release."""
    return {"profile_id": str(profile.id), "facts": []}


@router.delete("/{mid}", status_code=204)
async def delete_memory(
    mid: str,
    profile: Profile = Depends(get_verified_profile),
) -> None:
    """Delete a specific memory entry. Mem0 integration will be added in a future release."""
    pass
