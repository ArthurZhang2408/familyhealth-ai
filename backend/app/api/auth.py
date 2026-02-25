from fastapi import APIRouter, Depends

from app.core.security import CurrentAccount, get_current_account

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/verify")
async def verify_token(account: CurrentAccount = Depends(get_current_account)) -> dict:
    """Verify Supabase JWT and return internal session info."""
    return {"account_id": str(account.id), "email": account.email}


@router.get("/me")
async def get_me(account: CurrentAccount = Depends(get_current_account)) -> dict:
    """Get current account info from token."""
    return {"account_id": str(account.id), "email": account.email}
