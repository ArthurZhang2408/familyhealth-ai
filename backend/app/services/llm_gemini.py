from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

from app.services.llm import (
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMTask,
    StreamChunk,
    ToolCallResponse,
)

# Gemini uses "model" instead of "assistant" for the AI role
_ROLE_MAP = {"assistant": "model", "user": "user", "system": "user"}


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        diagnosis_model: str = "gemini-2.5-flash",
        report_model: str = "gemini-2.5-flash",
        default_model: str = "gemini-2.5-flash-lite",
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._diagnosis_model = diagnosis_model
        self._report_model = report_model
        self._default_model = default_model

    def _select_model(self, task: LLMTask, has_images: bool = False) -> str:
        if task == LLMTask.DIAGNOSIS:
            return self._diagnosis_model
        if task == LLMTask.REPORT_ANALYSIS:
            return self._report_model
        # Flash Lite supports multimodal — no need to upgrade for chat images
        return self._default_model

    @staticmethod
    def _build_parts(msg: LLMMessage) -> list[types.Part]:
        """Build Gemini Part list from an LLMMessage, handling text + images."""
        parts: list[types.Part] = []
        if msg.content:
            parts.append(types.Part(text=msg.content))
        if msg.image_parts:
            for img in msg.image_parts:
                parts.append(types.Part.from_bytes(data=img.data, mime_type=img.mime_type))
        # Gemini API requires at least one part per Content block
        if not parts:
            parts.append(types.Part(text=""))
        return parts

    def _build_config(self, request: LLMRequest) -> types.GenerateContentConfig:
        """Build Gemini config from LLMRequest, including tools if present."""
        config = types.GenerateContentConfig(
            system_instruction=request.system_prompt,
            temperature=request.temperature,
        )
        if request.max_tokens is not None:
            max_tokens = request.max_tokens
            # Thinking tokens count against max_output_tokens in Gemini.
            # Boost the limit so thinking doesn't eat the response budget.
            if request.thinking_budget is not None and request.thinking_budget != 0:
                max_tokens = max(max_tokens, 8000)
            config.max_output_tokens = max_tokens
        if request.response_format is not None:
            if request.tools:
                # JSON mode and tool calling are mutually exclusive in Gemini
                logger.warning(
                    "response_format ignored: Gemini cannot use JSON mode and "
                    "function calling simultaneously (task=%s)",
                    request.task,
                )
            else:
                config.response_mime_type = "application/json"
        if request.tools:
            config.tools = [types.Tool(function_declarations=request.tools)]
        if request.thinking_budget is not None and request.thinking_budget != 0:
            config.thinking_config = types.ThinkingConfig(
                include_thoughts=True,
                thinking_budget=request.thinking_budget,
            )
        return config

    @staticmethod
    def _extract_tool_calls(response) -> list[ToolCallResponse]:
        """Extract tool/function calls from a Gemini response."""
        tool_calls = []
        if not response.candidates:
            return tool_calls
        for part in response.candidates[0].content.parts:
            fc = getattr(part, "function_call", None)
            if fc and fc.name:
                tool_calls.append(
                    ToolCallResponse(
                        id=f"tc_{uuid.uuid4().hex[:12]}",
                        name=fc.name,
                        arguments=dict(fc.args) if fc.args else {},
                    )
                )
        return tool_calls

    async def generate(self, request: LLMRequest) -> LLMResponse:
        has_images = any(m.image_parts for m in request.messages if m.image_parts)
        model = request.model or self._select_model(request.task, has_images=has_images)

        contents = [
            types.Content(
                role=_ROLE_MAP.get(msg.role, msg.role),
                parts=self._build_parts(msg),
            )
            for msg in request.messages
        ]

        config = self._build_config(request)

        response = await self._client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        usage = {}
        if response.usage_metadata:
            usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count or 0,
                "completion_tokens": (response.usage_metadata.candidates_token_count or 0),
            }

        # Check for tool calls
        tool_calls = self._extract_tool_calls(response)

        # Extract text content, skipping thought parts
        content = ""
        if not tool_calls:
            try:
                parts = response.candidates[0].content.parts
                text_parts = [
                    p.text
                    for p in parts
                    if hasattr(p, "text") and p.text and not getattr(p, "thought", False)
                ]
                content = "".join(text_parts) if text_parts else (response.text or "")
            except (IndexError, AttributeError):
                content = response.text or ""

        return LLMResponse(
            content=content,
            model=model,
            usage=usage,
            tool_calls=tool_calls or None,
            finish_reason="tool_calls" if tool_calls else "stop",
        )

    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        has_images = any(m.image_parts for m in request.messages if m.image_parts)
        model = request.model or self._select_model(request.task, has_images=has_images)

        contents = [
            types.Content(
                role=_ROLE_MAP.get(msg.role, msg.role),
                parts=self._build_parts(msg),
            )
            for msg in request.messages
        ]

        config = self._build_config(request)

        async for chunk in await self._client.aio.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        ):
            if not chunk.candidates:
                continue
            for part in chunk.candidates[0].content.parts:
                fc = getattr(part, "function_call", None)
                if fc and fc.name:
                    yield StreamChunk(
                        type="tool_call",
                        tool_calls=[
                            ToolCallResponse(
                                id=f"tc_{uuid.uuid4().hex[:12]}",
                                name=fc.name,
                                arguments=dict(fc.args) if fc.args else {},
                            )
                        ],
                    )
                elif getattr(part, "thought", False) and part.text:
                    yield StreamChunk(type="thinking_delta", content=part.text)
                elif hasattr(part, "text") and part.text:
                    yield StreamChunk(type="text_delta", content=part.text)

        yield StreamChunk(type="finish", finish_reason="stop")
