from __future__ import annotations

from collections.abc import AsyncIterator

from google import genai
from google.genai import types

from app.services.llm import LLMProvider, LLMRequest, LLMResponse, LLMTask

# Gemini uses "model" instead of "assistant" for the AI role
_ROLE_MAP = {"assistant": "model", "user": "user", "system": "user"}


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        diagnosis_model: str = "gemini-2.5-flash",
        default_model: str = "gemini-2.5-flash-lite",
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._diagnosis_model = diagnosis_model
        self._default_model = default_model

    def _select_model(self, task: LLMTask) -> str:
        if task == LLMTask.DIAGNOSIS:
            return self._diagnosis_model
        return self._default_model

    async def generate(self, request: LLMRequest) -> LLMResponse:
        model = self._select_model(request.task)

        contents = [
            types.Content(
                role=_ROLE_MAP.get(msg.role, msg.role),
                parts=[types.Part(text=msg.content)],
            )
            for msg in request.messages
        ]

        config = types.GenerateContentConfig(
            system_instruction=request.system_prompt,
            temperature=request.temperature,
        )
        if request.max_tokens is not None:
            config.max_output_tokens = request.max_tokens
        if request.response_format is not None:
            config.response_mime_type = "application/json"

        response = await self._client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        usage = {}
        if response.usage_metadata:
            usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count or 0,
                "completion_tokens": response.usage_metadata.candidates_token_count or 0,
            }

        return LLMResponse(
            content=response.text or "",
            model=model,
            usage=usage,
        )

    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[str]:
        model = self._select_model(request.task)

        contents = [
            types.Content(
                role=_ROLE_MAP.get(msg.role, msg.role),
                parts=[types.Part(text=msg.content)],
            )
            for msg in request.messages
        ]

        config = types.GenerateContentConfig(
            system_instruction=request.system_prompt,
            temperature=request.temperature,
        )
        if request.max_tokens is not None:
            config.max_output_tokens = request.max_tokens
        if request.response_format is not None:
            config.response_mime_type = "application/json"

        async for chunk in await self._client.aio.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        ):
            if chunk.text:
                yield chunk.text
