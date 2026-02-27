import logging
import time
from typing import Any
from uuid import UUID

import httpx
import jwt as pyjwt
from fastapi import HTTPException, Request
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

_JWKS_CACHE: dict[str, Any] = {}
_JWKS_FETCHED_AT: float = 0.0
_JWKS_TTL = 3600.0  # re-fetch public keys every hour


async def _fetch_jwks() -> None:
    """Fetch Supabase JWKS and populate the in-memory key cache."""
    global _JWKS_FETCHED_AT
    url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    for key_data in resp.json().get("keys", []):
        _JWKS_CACHE[key_data["kid"]] = pyjwt.algorithms.ECAlgorithm.from_jwk(key_data)
    _JWKS_FETCHED_AT = time.monotonic()


async def _get_public_key(kid: str) -> Any:
    """Return the EC public key for kid, refreshing the cache when stale."""
    if not _JWKS_CACHE or (time.monotonic() - _JWKS_FETCHED_AT) > _JWKS_TTL:
        await _fetch_jwks()
    if kid in _JWKS_CACHE:
        return _JWKS_CACHE[kid]
    # Unknown kid — re-fetch once to handle key rotation
    await _fetch_jwks()
    if kid not in _JWKS_CACHE:
        raise ValueError(f"kid {kid!r} not found in Supabase JWKS")
    return _JWKS_CACHE[kid]


class CurrentAccount(BaseModel):
    id: UUID
    email: str | None = None


def _extract_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    return auth_header.removeprefix("Bearer ")


async def get_current_account(request: Request) -> CurrentAccount:
    """Verify Supabase JWT (ES256) against JWKS and return the authenticated account."""
    token = _extract_token(request)
    try:
        kid = pyjwt.get_unverified_header(token).get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="JWT missing kid")

        public_key = await _get_public_key(kid)
        payload = pyjwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            audience="authenticated",
            issuer=f"{settings.supabase_url}/auth/v1",
            leeway=10,
        )
    except pyjwt.PyJWTError as e:
        logger.warning("JWT verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid or expired token") from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error("JWT processing error: %s", e)
        raise HTTPException(status_code=401, detail="Invalid or expired token") from e

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing subject claim")

    return CurrentAccount(id=UUID(sub), email=payload.get("email"))
