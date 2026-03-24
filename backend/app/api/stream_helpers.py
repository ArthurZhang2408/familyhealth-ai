"""Shared SSE streaming utilities for chat and diagnosis endpoints."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator

from fastapi.responses import StreamingResponse

_SSE_KEEPALIVE_TIMEOUT = 30  # seconds


async def sse_event_stream(
    queue: asyncio.Queue,
    sentinel: object,
    logger: logging.Logger,
    *,
    log_context: str = "",
) -> AsyncGenerator[str, None]:
    """Consume an event queue and yield SSE-formatted strings.

    Sends keepalive comments every ``_SSE_KEEPALIVE_TIMEOUT`` seconds to
    prevent reverse-proxy idle timeouts (e.g. Railway's 60 s limit).

    Args:
        queue: The event queue populated by a background processing task.
        sentinel: The object that signals the end of the stream.
        logger: Logger for stream lifecycle messages.
        log_context: Optional suffix appended to log messages (e.g. ``"session=<id>"``).
    """
    stream_start = time.monotonic()
    events_sent = 0
    client_disconnected = False
    last_event_type = None
    ctx = f", {log_context}" if log_context else ""
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=_SSE_KEEPALIVE_TIMEOUT)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if item is sentinel:
                break
            last_event_type = item.type.value
            payload = {"type": item.type.value, **item.data}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            events_sent += 1
    except asyncio.CancelledError:
        client_disconnected = True
    finally:
        elapsed = int((time.monotonic() - stream_start) * 1000)
        if client_disconnected:
            logger.warning(
                "SSE client disconnected after %dms (%d events sent, last=%s%s)",
                elapsed,
                events_sent,
                last_event_type,
                ctx,
            )
        else:
            logger.info(
                "SSE stream completed in %dms (%d events sent%s)",
                elapsed,
                events_sent,
                ctx,
            )


def sse_response(
    queue: asyncio.Queue,
    sentinel: object,
    logger: logging.Logger,
    *,
    log_context: str = "",
) -> StreamingResponse:
    """Create a ``StreamingResponse`` wired to an SSE event stream."""
    return StreamingResponse(
        sse_event_stream(queue, sentinel, logger, log_context=log_context),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
