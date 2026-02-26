from __future__ import annotations

import logging
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import CurrentAccount, get_current_account
from app.models.profile import Profile
from app.services.context_builder import ContextBuilder
from app.services.llm import LLMRouter
from app.services.memory import MemoryService
from app.services.memory_extractor import MemoryExtractor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singletons — initialised on first call, shared across requests.
# Override via ``app.dependency_overrides`` in tests.
# ---------------------------------------------------------------------------

_memory_service: MemoryService | None = None
_llm_router: LLMRouter | None = None
_context_builder: ContextBuilder | None = None
_memory_extractor: MemoryExtractor | None = None


async def get_verified_profile(
    pid: UUID,
    account: CurrentAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    """Verify the authenticated account owns the requested profile."""
    result = await db.execute(
        select(Profile).where(Profile.id == pid, Profile.deleted_at.is_(None))
    )
    profile = result.scalar_one_or_none()
    if not profile or profile.account_id != account.id:
        raise AppError(status_code=404, detail="Profile not found", code="NOT_FOUND")
    return profile


def get_memory_service() -> MemoryService:
    """Return a singleton MemoryService backed by a lazily-initialised Mem0 client."""
    global _memory_service  # noqa: PLW0603
    if _memory_service is None:
        from mem0 import Memory

        from app.services.memory import build_mem0_config

        config = build_mem0_config(settings)
        client = Memory.from_config(config)
        _memory_service = MemoryService(client)
        logger.info("Mem0 client initialised")
    return _memory_service


def get_llm_router() -> LLMRouter:
    """Return a singleton LLMRouter with Gemini + Qwen providers."""
    global _llm_router  # noqa: PLW0603
    if _llm_router is None:
        from app.services.llm_gemini import GeminiProvider
        from app.services.llm_qwen import QwenProvider

        gemini = GeminiProvider(
            api_key=settings.gemini_api_key,
            diagnosis_model=settings.gemini_diagnosis_model,
            default_model=settings.gemini_flash_model,
        )
        qwen = QwenProvider(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            model=settings.qwen_model,
        )
        _llm_router = LLMRouter({"gemini": gemini, "qwen": qwen})
        logger.info("LLM router initialised (gemini + qwen)")
    return _llm_router


def get_context_builder() -> ContextBuilder:
    """Return a singleton ContextBuilder backed by MemoryService."""
    global _context_builder  # noqa: PLW0603
    if _context_builder is None:
        _context_builder = ContextBuilder(get_memory_service())
        logger.info("ContextBuilder initialised")
    return _context_builder


def get_memory_extractor() -> MemoryExtractor:
    """Return a singleton MemoryExtractor."""
    global _memory_extractor  # noqa: PLW0603
    if _memory_extractor is None:
        _memory_extractor = MemoryExtractor(get_memory_service())
        logger.info("MemoryExtractor initialised")
    return _memory_extractor
