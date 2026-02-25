from __future__ import annotations

from collections.abc import AsyncIterator

import openai

from app.services.llm import LLMProvider, LLMRequest, LLMResponse


class QwenProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "qwen/qwen-2.5-72b-instruct",
    ) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def _build_messages(self, request: LLMRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": request.system_prompt},
        ]
        messages.extend({"role": msg.role, "content": msg.content} for msg in request.messages)
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

    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[str]:
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
            if chunk.choices and chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
