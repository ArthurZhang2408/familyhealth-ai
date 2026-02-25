from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import Profile


class ProfileService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, profile_id: UUID) -> Profile | None:
        result = await self.db.execute(
            select(Profile).where(Profile.id == profile_id, Profile.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_by_account(self, account_id: UUID) -> list[Profile]:
        result = await self.db.execute(
            select(Profile).where(Profile.account_id == account_id, Profile.deleted_at.is_(None))
        )
        return list(result.scalars().all())
