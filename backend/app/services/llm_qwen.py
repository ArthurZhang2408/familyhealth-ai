from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator

import openai

from app.services.llm import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    StreamChunk,
    ToolCallResponse,
)

logger = logging.getLogger(__name__)

# Default params to strip — Gemini-specific, never valid for OpenAI-compatible APIs
_DEFAULT_EXCLUDED = frozenset({"enable_thinking"})


class QwenProvider(LLMProvider):
    """OpenAI-compatible LLM provider (Cerebras, Qwen/Ollama, OpenRouter, etc.).

    Parameters
    ----------
    excluded_params : frozenset[str]
        ``request.extra`` keys to silently drop (the backend rejects them).
    promoted_params : frozenset[str]
        ``request.extra`` keys to move to **top-level** kwargs on
        ``chat.completions.create`` instead of ``extra_body``.
        Use for params that the OpenAI SDK accepts natively
        (e.g. ``reasoning_effort``).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "qwen3.5:397b",
        *,
        excluded_params: frozenset[str] | None = None,
        promoted_params: frozenset[str] | None = None,
    ) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._excluded = excluded_params if excluded_params is not None else _DEFAULT_EXCLUDED
        self._promoted = promoted_params or frozenset()

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

    @staticmethod
    def _build_tools(request: LLMRequest) -> list[dict] | None:
        """Convert LLMRequest tools to OpenAI function-calling format."""
        if not request.tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {}),
                },
            }
            for t in request.tools
        ]

    @staticmethod
    def _extract_from_reasoning(reasoning: str) -> str:
        """Best-effort answer extraction from the thinking block.

        Thinking models sometimes complete their reasoning and place the
        answer at the very end, but ``content`` stays empty because the
        token budget ran out right after the answer.  We look for common
        patterns:
        - A final line after "Answer:" / "Topic:" / "Result:" / "Output:"
        - The last non-empty line if it's short (≤ 80 chars) and looks
          like a direct answer rather than mid-thought reasoning.
        """
        import re

        # Pattern: explicit answer marker near the end
        m = re.search(
            r"(?:^|\n)\s*(?:Answer|Topic|Result|Output|Label|Final answer)\s*[:：]\s*(.+)",
            reasoning,
            re.IGNORECASE,
        )
        if m:
            answer = m.group(1).strip().strip('"\'')
            if answer:
                logger.info("Extracted answer from reasoning field: %r", answer[:100])
                return answer

        # Fallback: last non-empty line if it's short and doesn't look like
        # mid-reasoning (no bullet points, no "**", no step numbering)
        lines = [ln.strip() for ln in reasoning.strip().splitlines() if ln.strip()]
        if lines:
            last = lines[-1].strip('"\'').strip()
            if (
                len(last) <= 80
                and not last.startswith(("-", "*", "•"))
                and not re.match(r"^\d+\.", last)
                and "**" not in last
            ):
                logger.info("Extracted last line from reasoning as answer: %r", last[:100])
                return last

        return ""

    def _apply_extra(self, request: LLMRequest, kwargs: dict) -> None:
        """Route ``request.extra`` params to the right place in *kwargs*.

        * Keys in ``self._excluded`` are silently dropped.
        * Keys in ``self._promoted`` become top-level kwargs (native SDK params).
        * Everything else goes into ``extra_body``.
        """
        if not request.extra:
            return
        extra_body: dict = {}
        for k, v in request.extra.items():
            if k in self._excluded:
                continue
            if k in self._promoted:
                kwargs[k] = v
            else:
                extra_body[k] = v
        if extra_body:
            kwargs["extra_body"] = extra_body

    @staticmethod
    def _parse_tool_calls(
        message: openai.types.chat.ChatCompletionMessage,
    ) -> list[ToolCallResponse] | None:
        """Extract tool calls from an OpenAI chat completion message."""
        if not message.tool_calls:
            return None
        results = []
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            results.append(
                ToolCallResponse(
                    id=tc.id or f"tc_{uuid.uuid4().hex[:12]}",
                    name=tc.function.name,
                    arguments=args,
                )
            )
        return results or None

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

        tools = self._build_tools(request)
        if tools:
            kwargs["tools"] = tools
            if request.tool_choice:
                kwargs["tool_choice"] = request.tool_choice
        self._apply_extra(request, kwargs)

        response = await self._client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
            }

        tool_calls = self._parse_tool_calls(choice.message)
        finish = str(choice.finish_reason) if choice.finish_reason else "stop"

        content = choice.message.content or ""
        if not content and not tool_calls:
            # Thinking models (Qwen3.5, gpt-oss-120b) put their reasoning in a
            # separate ``reasoning`` field.  When max_tokens is exhausted on
            # thinking, content is empty.  As a last resort, try to salvage the
            # final line of the reasoning — sometimes the answer appears there.
            reasoning = getattr(choice.message, "reasoning", None) or ""
            if reasoning:
                content = self._extract_from_reasoning(reasoning)

            if not content:
                try:
                    raw = response.model_dump() if hasattr(response, "model_dump") else str(response)
                except Exception:
                    raw = repr(response)
                logger.warning(
                    "Empty content from %s (finish=%s, usage=%s, raw_content=%r, "
                    "message_keys=%s, full_response=%s)",
                    response.model,
                    finish,
                    usage,
                    choice.message.content,
                    (
                        list(vars(choice.message).keys())
                        if hasattr(choice.message, "__dict__")
                        else "N/A"
                    ),
                    str(raw)[:1000],
                )

        return LLMResponse(
            content=content,
            model=response.model,
            usage=usage,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else finish,
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

        tools = self._build_tools(request)
        if tools:
            kwargs["tools"] = tools
            if request.tool_choice:
                kwargs["tool_choice"] = request.tool_choice
        self._apply_extra(request, kwargs)

        response = await self._client.chat.completions.create(**kwargs)

        # Accumulate streaming tool call deltas
        # OpenAI streams tool calls as incremental argument fragments
        tc_accum: dict[int, dict] = {}  # index -> {id, name, args_buffer}

        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # Text content
            if delta.content is not None:
                yield StreamChunk(type="text_delta", content=delta.content)

            # Tool call deltas
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tc_accum:
                        tc_accum[idx] = {
                            "id": tc_delta.id or f"tc_{uuid.uuid4().hex[:12]}",
                            "name": (
                                tc_delta.function.name
                                if tc_delta.function and tc_delta.function.name
                                else ""
                            ),
                            "args": "",
                        }
                    acc = tc_accum[idx]
                    if tc_delta.function and tc_delta.function.name:
                        acc["name"] = tc_delta.function.name
                    if tc_delta.function and tc_delta.function.arguments:
                        acc["args"] += tc_delta.function.arguments

        # Emit accumulated tool calls at end of stream
        if tc_accum:
            tool_calls = []
            for acc in tc_accum.values():
                try:
                    args = json.loads(acc["args"])
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(
                    ToolCallResponse(
                        id=acc["id"],
                        name=acc["name"],
                        arguments=args,
                    )
                )
            yield StreamChunk(type="tool_call", tool_calls=tool_calls)

        yield StreamChunk(
            type="finish",
            finish_reason="tool_calls" if tc_accum else "stop",
        )
