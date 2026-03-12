"""Request logging middleware with request ID propagation.

Every HTTP request gets a unique request ID that is:
1. Injected into all log records during that request (via contextvars)
2. Returned in the ``X-Request-ID`` response header
3. Logged with method, path, status code, and duration on completion

Uses raw ASGI (not BaseHTTPMiddleware) to avoid buffering streaming responses.
"""

import contextvars
import logging
import time
import uuid
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

# Context var holding the current request ID — accessible from any code
# running within the request lifecycle.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_access_logger = logging.getLogger("access")


class RequestIDFilter(logging.Filter):
    """Inject the current request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")  # type: ignore[attr-defined]
        return True


class RequestIDFormatter(logging.Formatter):
    """Formatter that injects request_id if missing (e.g. startup/third-party logs)."""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get("-")  # type: ignore[attr-defined]
        return super().format(record)


class RequestLoggingMiddleware:
    """Log every HTTP request with method, path, status, duration, and request ID.

    Implemented as raw ASGI middleware to avoid BaseHTTPMiddleware's
    response buffering, which breaks SSE/streaming.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = uuid.uuid4().hex[:12]
        request_id_var.set(rid)

        method = scope.get("method", "?")
        path = scope.get("path", "?")
        start = time.monotonic()
        status_code = 500  # default if response never starts

        async def send_with_tracking(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                # Inject X-Request-ID header
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", rid.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_tracking)
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            # Skip noisy health checks
            if path == "/health":
                return
            log_fn = _access_logger.warning if status_code >= 400 else _access_logger.info
            log_fn(
                "%s %s %d %dms rid=%s",
                method,
                path,
                status_code,
                duration_ms,
                rid,
            )
