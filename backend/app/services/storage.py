"""Supabase Storage helper for persisting chat/diagnosis image attachments."""

from __future__ import annotations

import logging
import uuid

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BUCKET = "chat-images"


async def upload_chat_image(
    data: bytes,
    mime_type: str,
    profile_id: uuid.UUID,
    filename: str | None = None,
) -> str:
    """Upload image bytes to Supabase Storage and return the public URL.

    Files are stored under ``chat-images/<profile_id>/<unique_id>.<ext>``.
    Returns the full public URL for the uploaded object.
    """
    ext = _mime_to_ext(mime_type)
    object_path = f"{profile_id}/{uuid.uuid4().hex[:12]}.{ext}"

    storage_url = f"{settings.supabase_url}/storage/v1/object/{BUCKET}/{object_path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "apikey": settings.supabase_service_key,
        "Content-Type": mime_type,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(storage_url, content=data, headers=headers, timeout=30)
        resp.raise_for_status()

    public_url = f"{settings.supabase_url}/storage/v1/object/public/{BUCKET}/{object_path}"
    logger.info("Uploaded chat image: %s (%d bytes)", object_path, len(data))
    return public_url


def _mime_to_ext(mime_type: str) -> str:
    return {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "application/pdf": "pdf",
    }.get(mime_type, "bin")
