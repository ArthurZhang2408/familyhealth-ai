from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_verified_profile
from app.core.database import get_db
from app.models.profile import Profile
from app.schemas.action_log import ActionLogResponse, ActionType
from app.schemas.common import PaginatedResponse
from app.services.action_log import ActionLogService

router = APIRouter(prefix="/profiles", tags=["activity"])


@router.get("/{pid}/activity", response_model=PaginatedResponse[ActionLogResponse])
async def list_activity(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    action_type: ActionType | None = Query(None),
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ActionLogResponse]:
    """Paginated activity feed for a profile (newest first)."""
    svc = ActionLogService(db)
    entries, total = await svc.list_for_profile(profile.id, page, per_page, action_type)
    return PaginatedResponse(
        items=[ActionLogResponse.model_validate(e) for e in entries],
        total=total,
        page=page,
        per_page=per_page,
    )
