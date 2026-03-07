"""Shared helpers for handling file uploads across API endpoints."""

from fastapi import HTTPException, UploadFile

from app.services.llm import ImagePart

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "application/pdf",
}

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_FILES = 5


async def read_image_parts(files: list[UploadFile]) -> list[ImagePart]:
    """Convert uploaded files into ImagePart objects for multimodal LLM input.

    Validates file count, MIME type, and file size. Returns empty list if no
    files provided.
    """
    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files ({len(files)}). Max: {MAX_FILES}.",
        )

    parts: list[ImagePart] = []
    for f in files:
        content_type = f.content_type or "application/octet-stream"
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {content_type}. "
                f"Allowed: {', '.join(sorted(ALLOWED_IMAGE_TYPES))}",
            )

        # Read in chunks to cap memory before loading the full file
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await f.read(1024 * 1024)  # 1 MB chunks
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_IMAGE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"File too large (>{MAX_IMAGE_SIZE // (1024 * 1024)} MB). Max: 10 MB.",
                )
            chunks.append(chunk)

        parts.append(ImagePart(data=b"".join(chunks), mime_type=content_type))
    return parts
