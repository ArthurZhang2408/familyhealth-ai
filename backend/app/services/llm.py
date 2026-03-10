from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LLMTask(StrEnum):
    DIAGNOSIS = "diagnosis"
    REPORT_ANALYSIS = "report_analysis"
    MEMORY_EXTRACTION = "memory_extraction"
    CHAT = "chat"
    SUMMARIZATION = "summarization"
    FACT_EXTRACTION = "fact_extraction"


class ImagePart(BaseModel):
    """Binary image/document data for multimodal LLM input."""

    data: bytes
    mime_type: str  # "application/pdf", "image/jpeg", "image/png"

    model_config = {"arbitrary_types_allowed": True}


class LLMMessage(BaseModel):
    role: str
    content: str
    image_parts: list[ImagePart] | None = None

    model_config = {"arbitrary_types_allowed": True}


class ToolCallResponse(BaseModel):
    """A tool invocation returned by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


class LLMRequest(BaseModel):
    task: LLMTask
    system_prompt: str
    messages: list[LLMMessage]
    temperature: float = 0.7
    max_tokens: int | None = None
    response_format: dict | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | None = None  # "auto" | "any" | "none"
    thinking_budget: int | None = None  # None=disabled, -1=automatic
    extra: dict[str, Any] | None = None  # Provider-specific params (e.g. enable_thinking)


class LLMResponse(BaseModel):
    content: str
    model: str
    usage: dict[str, int]
    raw_response: dict | None = None
    tool_calls: list[ToolCallResponse] | None = None
    finish_reason: str | None = None  # "stop" | "tool_calls"


@dataclass
class StreamChunk:
    """A chunk emitted during streaming LLM generation."""

    type: Literal["text_delta", "thinking_delta", "tool_call", "finish"]
    content: str = ""
    tool_calls: list[ToolCallResponse] = field(default_factory=list)
    finish_reason: str | None = None


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse: ...

    @abstractmethod
    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]: ...


class LLMRouter:
    # Fallback defaults when no env override and no Cerebras
    _BASE_DEFAULTS: dict[LLMTask, str] = {
        LLMTask.DIAGNOSIS: "gemini",
        LLMTask.REPORT_ANALYSIS: "gemini",
        LLMTask.MEMORY_EXTRACTION: "qwen",
        LLMTask.CHAT: "qwen",
        LLMTask.SUMMARIZATION: "qwen",
        LLMTask.FACT_EXTRACTION: "qwen",
    }

    # Tasks that Cerebras should take over when available (no env override)
    _CEREBRAS_ELIGIBLE: set[LLMTask] = {
        LLMTask.CHAT,
        LLMTask.DIAGNOSIS,
        LLMTask.MEMORY_EXTRACTION,
        LLMTask.SUMMARIZATION,
        LLMTask.FACT_EXTRACTION,
    }

    def __init__(
        self,
        providers: dict[str, LLMProvider],
        route_overrides: dict[LLMTask, str] | None = None,
    ) -> None:
        self._providers = providers
        self._routing = self._build_routing(providers, route_overrides or {})
        logger.info("LLM routing: %s", {k.value: v for k, v in self._routing.items()})

    def _build_routing(
        self,
        providers: dict[str, LLMProvider],
        overrides: dict[LLMTask, str],
    ) -> dict[LLMTask, str]:
        """Build the routing table from defaults, Cerebras auto-upgrade, and env overrides."""
        routing = dict(self._BASE_DEFAULTS)

        # Auto-upgrade eligible tasks to Cerebras when available
        if "cerebras" in providers:
            for task in self._CEREBRAS_ELIGIBLE:
                routing[task] = "cerebras"

        # Env overrides take priority over everything
        for task, provider_name in overrides.items():
            if provider_name and provider_name in providers:
                routing[task] = provider_name
            elif provider_name:
                logger.warning(
                    "LLM route override '%s=%s' ignored — provider not registered",
                    task.value,
                    provider_name,
                )

        return routing

    def _resolve(self, request: LLMRequest) -> LLMProvider:
        # Auto-upgrade to Gemini when images are present (Qwen doesn't support multimodal)
        has_images = any(m.image_parts for m in request.messages if m.image_parts)
        provider_name = "gemini" if has_images else self._routing[request.task]
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ValueError(f"No provider registered for '{provider_name}'")
        return provider

    def _get_fallback(self, request: LLMRequest) -> LLMProvider | None:
        """Get a fallback provider different from the primary one."""
        primary = self._routing[request.task]
        # Try qwen first, then gemini
        for fallback_name in ("qwen", "gemini"):
            if fallback_name != primary and fallback_name in self._providers:
                return self._providers[fallback_name]
        return None

    async def route(self, request: LLMRequest) -> LLMResponse:
        provider = self._resolve(request)
        try:
            return await provider.generate(request)
        except Exception as exc:
            fallback = self._get_fallback(request)
            if fallback is None:
                raise
            logger.warning(
                "Primary provider failed for task=%s (%s), falling back: %s",
                request.task.value,
                type(exc).__name__,
                exc,
            )
            return await fallback.generate(request)

    async def route_stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        provider = self._resolve(request)
        try:
            async for chunk in provider.generate_stream(request):
                yield chunk
        except Exception as exc:
            fallback = self._get_fallback(request)
            if fallback is None:
                raise
            logger.warning(
                "Primary provider failed for task=%s (%s), falling back: %s",
                request.task.value,
                type(exc).__name__,
                exc,
            )
            async for chunk in fallback.generate_stream(request):
                yield chunk
