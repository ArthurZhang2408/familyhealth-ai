import logging

import httpx
from fastapi import APIRouter, Depends, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_memory_service
from app.core.config import settings
from app.core.database import get_db
from app.core.security import CurrentAccount, get_current_account
from app.models.profile import Profile
from app.services.memory import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/verify")
async def verify_token(account: CurrentAccount = Depends(get_current_account)) -> dict:
    """Verify Supabase JWT and return internal session info."""
    return {"account_id": str(account.id), "email": account.email}


@router.get("/me")
async def get_me(account: CurrentAccount = Depends(get_current_account)) -> dict:
    """Get current account info from token."""
    return {"account_id": str(account.id), "email": account.email}


@router.delete("/account", status_code=204)
async def delete_account(
    account: CurrentAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
    memory_service: MemoryService = Depends(get_memory_service),
) -> Response:
    """Permanently delete the authenticated user's account and all associated data.

    Deletion order: Mem0 memories → DB profiles (CASCADE) → Supabase auth user.
    Each step is best-effort so partial failures don't leave the user stuck.
    """
    # 1. Fetch all profiles (including soft-deleted) for this account
    result = await db.execute(select(Profile).where(Profile.account_id == account.id))
    profiles = result.scalars().all()
    logger.info("Deleting account %s — %d profile(s)", account.id, len(profiles))

    # 2. Best-effort Mem0 memory cleanup per profile
    for profile in profiles:
        try:
            await memory_service.delete_all(profile.id)
        except Exception:
            logger.warning(
                "Mem0 cleanup failed for profile %s — continuing",
                profile.id,
                exc_info=True,
            )

    # 3. Hard-delete all profile rows — CASCADE handles child tables
    await db.execute(delete(Profile).where(Profile.account_id == account.id))
    await db.commit()

    # 4. Delete Supabase auth user (best-effort — data is already gone)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.delete(
                f"{settings.supabase_url}/auth/v1/admin/users/{account.id}",
                headers={
                    "apikey": settings.supabase_service_key,
                    "Authorization": f"Bearer {settings.supabase_service_key}",
                },
            )
            if resp.status_code == 404:
                logger.info("Supabase user %s already deleted", account.id)
            elif resp.is_error:
                logger.warning(
                    "Supabase user deletion returned %d for %s",
                    resp.status_code,
                    account.id,
                )
    except Exception:
        logger.warning(
            "Supabase user deletion failed for %s — orphaned auth user",
            account.id,
            exc_info=True,
        )

    return Response(status_code=204)
