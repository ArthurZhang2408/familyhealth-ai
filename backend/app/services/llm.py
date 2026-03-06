from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar, Literal

from pydantic import BaseModel


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

    type: Literal["text_delta", "tool_call", "finish"]
    content: str = ""
    tool_calls: list[ToolCallResponse] = field(default_factory=list)
    finish_reason: str | None = None


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse: ...

    @abstractmethod
    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]: ...


class LLMRouter:
    ROUTING_TABLE: ClassVar[dict[LLMTask, str]] = {
        LLMTask.DIAGNOSIS: "gemini",
        LLMTask.REPORT_ANALYSIS: "gemini",
        LLMTask.MEMORY_EXTRACTION: "qwen",
        LLMTask.CHAT: "qwen",
        LLMTask.SUMMARIZATION: "qwen",
        LLMTask.FACT_EXTRACTION: "qwen",
    }

    def __init__(self, providers: dict[str, LLMProvider]) -> None:
        self._providers = providers

    def _resolve(self, request: LLMRequest) -> LLMProvider:
        # Auto-upgrade to Gemini when images are present (Qwen doesn't support multimodal)
        has_images = any(m.image_parts for m in request.messages if m.image_parts)
        provider_name = "gemini" if has_images else self.ROUTING_TABLE[request.task]
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ValueError(f"No provider registered for '{provider_name}'")
        return provider

    async def route(self, request: LLMRequest) -> LLMResponse:
        provider = self._resolve(request)
        return await provider.generate(request)

    async def route_stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        provider = self._resolve(request)
        async for chunk in provider.generate_stream(request):
            yield chunk
