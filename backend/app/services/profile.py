from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import Profile
from app.schemas.profile import ProfileCreate, ProfileUpdate


class ProfileService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, account_id: UUID, data: ProfileCreate) -> Profile:
        """Create a profile. Raises ValueError if 'self' profile already exists."""
        if data.relationship == "self":
            if await self._has_self_profile(account_id):
                raise ValueError("A 'self' profile already exists for this account")

        # Serialize nested Pydantic models to dicts for JSONB storage
        dump = data.model_dump()
        profile = Profile(account_id=account_id, **dump)
        self.db.add(profile)
        await self.db.flush()
        await self.db.refresh(profile)
        return profile

    async def list_paginated(
        self, account_id: UUID, page: int, per_page: int
    ) -> tuple[list[Profile], int]:
        """Return (profiles, total_count) for the given account."""
        base = select(Profile).where(
            Profile.account_id == account_id, Profile.deleted_at.is_(None)
        )
        count_result = await self.db.execute(select(func.count()).select_from(base.subquery()))
        total = count_result.scalar_one()

        result = await self.db.execute(
            base.order_by(Profile.created_at).offset((page - 1) * per_page).limit(per_page)
        )
        return list(result.scalars().all()), total

    async def get_by_id(self, profile_id: UUID) -> Profile | None:
        result = await self.db.execute(
            select(Profile).where(Profile.id == profile_id, Profile.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def update(self, profile: Profile, data: ProfileUpdate) -> Profile:
        """Update profile fields. Raises ValueError on self-conflict."""
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise ValueError("No fields to update")

        # If changing relationship to 'self', check for existing
        if (
            "relationship" in update_data
            and update_data["relationship"] == "self"
            and profile.relationship != "self"
        ):
            if await self._has_self_profile(profile.account_id, exclude_id=profile.id):
                raise ValueError("A 'self' profile already exists for this account")

        for field, value in update_data.items():
            setattr(profile, field, value)
        await self.db.flush()
        await self.db.refresh(profile)
        return profile

    async def soft_delete(self, profile: Profile) -> None:
        profile.deleted_at = func.now()
        await self.db.flush()

    async def _has_self_profile(self, account_id: UUID, exclude_id: UUID | None = None) -> bool:
        query = select(func.count()).where(
            Profile.account_id == account_id,
            Profile.relationship == "self",
            Profile.deleted_at.is_(None),
        )
        if exclude_id:
            query = query.where(Profile.id != exclude_id)
        result = await self.db.execute(query)
        return result.scalar_one() > 0
