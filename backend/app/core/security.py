from uuid import UUID

from fastapi import HTTPException, Request
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import settings


class CurrentAccount(BaseModel):
    id: UUID
    email: str | None = None


def _extract_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    return auth_header.removeprefix("Bearer ")


async def get_current_account(request: Request) -> CurrentAccount:
    """Verify Supabase JWT and return the authenticated account."""
    token = _extract_token(request)
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from e

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing subject claim")

    return CurrentAccount(id=UUID(sub), email=payload.get("email"))
