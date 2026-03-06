from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import openai

from app.services.llm import LLMProvider, LLMRequest, LLMResponse, StreamChunk

logger = logging.getLogger(__name__)


class QwenProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "qwen3.5:397b",
    ) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def _build_messages(self, request: LLMRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": request.system_prompt},
        ]
        for msg in request.messages:
            if msg.image_parts:
                logger.warning(
                    "QwenProvider received message with %d image_parts — "
                    "images will be dropped (Qwen is text-only). "
                    "This indicates a routing bug; images should route to Gemini.",
                    len(msg.image_parts),
                )
            messages.append({"role": msg.role, "content": msg.content})
        return messages

    async def generate(self, request: LLMRequest) -> LLMResponse:
        messages = self._build_messages(request)

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.response_format is not None:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
            }

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage=usage,
        )

    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        messages = self._build_messages(request)

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": request.temperature,
            "stream": True,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.response_format is not None:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)

        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content is not None:
                yield StreamChunk(type="text_delta", content=delta.content)

        yield StreamChunk(type="finish", finish_reason="stop")
