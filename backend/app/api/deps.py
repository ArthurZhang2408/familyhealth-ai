from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentAccount, get_current_account
from app.models.profile import Profile


async def get_verified_profile(
    pid: UUID,
    account: CurrentAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    """Verify the authenticated account owns the requested profile."""
    result = await db.execute(
        select(Profile).where(Profile.id == pid, Profile.deleted_at.is_(None))
    )
    profile = result.scalar_one_or_none()
    if not profile or profile.account_id != account.id:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile
