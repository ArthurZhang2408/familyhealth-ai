import copy
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_verified_profile
from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import CurrentAccount, get_current_account
from app.models.profile import Profile
from app.schemas.action_log import ActionType
from app.schemas.common import PaginatedResponse
from app.schemas.profile import ProfileCreate, ProfileResponse, ProfileUpdate
from app.services.action_log import ActionLogService
from app.services.profile import ProfileService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=PaginatedResponse[ProfileResponse])
async def list_profiles(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    account: CurrentAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ProfileResponse]:
    """List all profiles for the authenticated account."""
    svc = ProfileService(db)
    profiles, total = await svc.list_paginated(account.id, page, per_page)
    return PaginatedResponse(
        items=[ProfileResponse.model_validate(p) for p in profiles],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("", response_model=ProfileResponse, status_code=201)
async def create_profile(
    data: ProfileCreate,
    account: CurrentAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Create a new profile."""
    svc = ProfileService(db)
    try:
        profile = await svc.create(account.id, data)
    except ValueError as e:
        raise AppError(status_code=409, detail=str(e), code="CONFLICT")
    try:
        await ActionLogService(db).log(
            profile.id,
            account.id,
            ActionType.PROFILE_CREATED,
            {"name": data.name, "relationship": data.relationship},
        )
    except Exception:
        logger.exception("Failed to log profile_created for %s", profile.id)
    return ProfileResponse.model_validate(profile)


@router.get("/{pid}", response_model=ProfileResponse)
async def get_profile(
    profile: Profile = Depends(get_verified_profile),
) -> ProfileResponse:
    """Get profile details."""
    return ProfileResponse.model_validate(profile)


@router.patch("/{pid}", response_model=ProfileResponse)
async def update_profile(
    data: ProfileUpdate,
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Update profile fields (partial update)."""
    svc = ProfileService(db)
    update_data = data.model_dump(exclude_unset=True)
    fields_changed = list(update_data.keys())
    # Deep copy old values before mutation — JSONB fields are mutable references
    old_values = {f: copy.deepcopy(getattr(profile, f)) for f in fields_changed}
    try:
        profile = await svc.update(profile, data)
    except ValueError as e:
        msg = str(e)
        if "No fields" in msg:
            raise AppError(status_code=400, detail=msg, code="VALIDATION_ERROR")
        raise AppError(status_code=409, detail=msg, code="CONFLICT")
    try:
        await ActionLogService(db).log(
            profile.id,
            profile.account_id,
            ActionType.PROFILE_UPDATED,
            {"fields_changed": fields_changed, "old": old_values, "new": update_data},
        )
    except Exception:
        logger.exception("Failed to log profile_updated for %s", profile.id)
    return ProfileResponse.model_validate(profile)


@router.delete("/{pid}", status_code=204)
async def delete_profile(
    profile: Profile = Depends(get_verified_profile),
    account: CurrentAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete profile (30-day retention)."""
    svc = ProfileService(db)
    try:
        await ActionLogService(db).log(
            profile.id,
            account.id,
            ActionType.PROFILE_DELETED,
            {"name": profile.name, "relationship": profile.relationship},
        )
    except Exception:
        logger.exception("Failed to log profile_deleted for %s", profile.id)
    await svc.soft_delete(profile)
