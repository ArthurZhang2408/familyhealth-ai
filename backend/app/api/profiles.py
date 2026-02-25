from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_verified_profile
from app.core.database import get_db
from app.core.security import CurrentAccount, get_current_account
from app.models.profile import Profile
from app.schemas.common import PaginatedResponse
from app.schemas.profile import ProfileCreate, ProfileResponse, ProfileUpdate

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=PaginatedResponse[ProfileResponse])
async def list_profiles(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    account: CurrentAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ProfileResponse]:
    """List all profiles for the authenticated account."""
    base_query = select(Profile).where(
        Profile.account_id == account.id, Profile.deleted_at.is_(None)
    )
    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        base_query.offset((page - 1) * per_page).limit(per_page).order_by(Profile.created_at)
    )
    profiles = result.scalars().all()

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
    profile = Profile(account_id=account.id, **data.model_dump())
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
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
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    for field, value in update_data.items():
        setattr(profile, field, value)
    await db.flush()
    await db.refresh(profile)
    return ProfileResponse.model_validate(profile)


@router.delete("/{pid}", status_code=204)
async def delete_profile(
    profile: Profile = Depends(get_verified_profile),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete profile (30-day retention)."""
    profile.deleted_at = func.now()
    await db.flush()
