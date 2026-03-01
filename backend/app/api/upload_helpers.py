"""Shared helpers for handling file uploads across API endpoints."""

from fastapi import HTTPException, UploadFile

from app.services.llm import ImagePart

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB


async def read_image_parts(files: list[UploadFile]) -> list[ImagePart]:
    """Convert uploaded files into ImagePart objects for multimodal LLM input.

    Validates MIME type and file size. Returns empty list if no files provided.
    """
    parts: list[ImagePart] = []
    for f in files:
        content_type = f.content_type or "application/octet-stream"
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {content_type}. "
                f"Allowed: {', '.join(sorted(ALLOWED_IMAGE_TYPES))}",
            )
        data = await f.read()
        if len(data) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large ({len(data) // (1024 * 1024)} MB). Max: 10 MB.",
            )
        parts.append(ImagePart(data=data, mime_type=content_type))
    return parts
