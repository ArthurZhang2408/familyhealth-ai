"""Application-level rate limiting.

Keyed by auth token hash (per-user) with IP fallback.
In-memory storage — suitable for single-worker deployment.
"""

import hashlib

from fastapi import Request
from slowapi import Limiter


def _rate_limit_key(request: Request) -> str:
    """Key rate limits by auth token hash (per-user), falling back to IP."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header:
        return hashlib.sha256(auth_header.encode()).hexdigest()[:16]
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_rate_limit_key, default_limits=["30/minute"])
