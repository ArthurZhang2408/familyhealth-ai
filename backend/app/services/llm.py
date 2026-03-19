from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LLMTask(StrEnum):
    DIAGNOSIS = "diagnosis"
    REPORT_ANALYSIS = "report_analysis"
    CHAT = "chat"
    TOPIC_GENERATION = "topic_generation"
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
    model: str | None = None  # Router-injected model override; providers use this over their default


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


# ---------------------------------------------------------------------------
# Route option & fallback chain
# ---------------------------------------------------------------------------


@dataclass
class RouteOption:
    """A single (provider, model) pair in a fallback chain."""

    provider: str
    model: str


# ---------------------------------------------------------------------------
# Rate-limit tracker
# ---------------------------------------------------------------------------


class RateLimitTracker:
    """Tracks per-model cooldowns and daily exhaustion.

    - **Cooldown**: model hit a 429 with "retry in Xs" → skip until cooldown expires.
    - **Daily exhaustion**: model hit RPD limit → skip for the rest of the day.
    - **Unavailable**: model returned 404 → skip for a long time (1 hour).
    """

    def __init__(self) -> None:
        self._cooldowns: dict[str, float] = {}  # model → monotonic time when usable
        self._daily_exhausted: dict[str, str] = {}  # model → ISO date string

    def is_available(self, model: str) -> bool:
        # Check daily exhaustion first
        if model in self._daily_exhausted:
            if self._daily_exhausted[model] == date.today().isoformat():
                return False
            else:
                del self._daily_exhausted[model]

        # Check cooldown
        if model in self._cooldowns:
            if time.monotonic() < self._cooldowns[model]:
                return False
            else:
                del self._cooldowns[model]

        return True

    def record_error(self, model: str, exc: Exception) -> None:
        """Parse an error and set the appropriate cooldown/exhaustion."""
        exc_str = str(exc)

        # Check for daily RPD exhaustion (Gemini format)
        if "PerDay" in exc_str or "RPD" in exc_str.upper():
            self._daily_exhausted[model] = date.today().isoformat()
            logger.warning("Model %s: daily quota exhausted, skipping for today", model)
            return

        # Check for 404 — model doesn't exist
        if "404" in exc_str or "not_found" in exc_str:
            self._cooldowns[model] = time.monotonic() + 3600  # 1 hour
            logger.warning("Model %s: not found, skipping for 1 hour", model)
            return

        # Parse "retry in Xs" from error message
        retry_match = re.search(r"retry in (\d+(?:\.\d+)?)s", exc_str, re.IGNORECASE)
        if retry_match:
            delay = float(retry_match.group(1))
            self._cooldowns[model] = time.monotonic() + delay
            logger.warning("Model %s: rate limited, cooldown %.0fs", model, delay)
            return

        # Parse "retryDelay": "Xs" (Gemini JSON format)
        retry_match2 = re.search(r'"retryDelay"\s*:\s*"(\d+)s"', exc_str)
        if retry_match2:
            delay = float(retry_match2.group(1))
            self._cooldowns[model] = time.monotonic() + delay
            logger.warning("Model %s: rate limited, cooldown %.0fs", model, delay)
            return

        # Generic 429 without parseable delay — 60s cooldown
        if "429" in exc_str or "Too Many Requests" in exc_str:
            self._cooldowns[model] = time.monotonic() + 60
            logger.warning("Model %s: rate limited (no retry-after), cooldown 60s", model)
            return

        # Other errors — short cooldown to avoid hammering
        self._cooldowns[model] = time.monotonic() + 10
        logger.warning("Model %s: error, 10s cooldown: %s", model, type(exc).__name__)

    def status(self) -> dict[str, str]:
        """Return human-readable status for logging."""
        now = time.monotonic()
        today = date.today().isoformat()
        result = {}
        for model, until in self._cooldowns.items():
            if until > now:
                result[model] = f"cooldown {int(until - now)}s"
        for model, day in self._daily_exhausted.items():
            if day == today:
                result[model] = "exhausted today"
        return result


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class LLMRouter:
    # Prod-safe defaults — all tasks route to Gemini.
    # Dev environments override these via LLM_ROUTE_* env vars.
    _BASE_DEFAULTS: dict[LLMTask, str] = {
        LLMTask.DIAGNOSIS: "gemini",
        LLMTask.REPORT_ANALYSIS: "gemini",
        LLMTask.CHAT: "gemini",
        LLMTask.TOPIC_GENERATION: "gemini",
        LLMTask.SUMMARIZATION: "gemini",
        LLMTask.FACT_EXTRACTION: "gemini",
    }

    def __init__(
        self,
        providers: dict[str, LLMProvider],
        route_overrides: dict[LLMTask, str] | None = None,
        fallback_chains: dict[LLMTask, list[RouteOption]] | None = None,
    ) -> None:
        self._providers = providers
        self._routing = self._build_routing(providers, route_overrides or {})
        self._fallback_chains = fallback_chains or {}
        self._rate_tracker = RateLimitTracker()
        logger.info("LLM routing: %s", {k.value: v for k, v in self._routing.items()})
        if self._fallback_chains:
            chains_summary = {
                k.value: [f"{o.provider}:{o.model}" for o in v]
                for k, v in self._fallback_chains.items()
            }
            logger.info("LLM fallback chains: %s", chains_summary)

    def _build_routing(
        self,
        providers: dict[str, LLMProvider],
        overrides: dict[LLMTask, str],
    ) -> dict[LLMTask, str]:
        """Build the routing table from defaults + explicit env overrides."""
        routing = dict(self._BASE_DEFAULTS)

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
        _, provider = self._resolve_named(request)
        return provider

    def _resolve_named(self, request: LLMRequest) -> tuple[str, LLMProvider]:
        """Resolve the provider for a request, returning (name, provider)."""
        has_images = any(m.image_parts for m in request.messages if m.image_parts)
        provider_name = "gemini" if has_images else self._routing[request.task]
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ValueError(f"No provider registered for '{provider_name}'")
        return provider_name, provider

    def _get_chain(self, request: LLMRequest) -> list[RouteOption]:
        """Get the fallback chain for a task, filtering to available models."""
        chain = self._fallback_chains.get(request.task, [])
        if not chain:
            # No chain configured — use routing table (legacy behavior)
            return []
        return [
            opt for opt in chain
            if opt.provider in self._providers
            and self._rate_tracker.is_available(opt.model)
        ]

    async def route(
        self, request: LLMRequest, *, trace: dict[str, Any] | None = None
    ) -> LLMResponse:
        chain = self._get_chain(request)

        if chain:
            return await self._route_with_chain(request, chain, trace)

        # Legacy fallback (no chain configured): primary → one fallback
        return await self._route_legacy(request, trace)

    async def route_stream(
        self, request: LLMRequest, *, trace: dict[str, Any] | None = None
    ) -> AsyncIterator[StreamChunk]:
        chain = self._get_chain(request)

        if chain:
            async for chunk in self._route_stream_with_chain(request, chain, trace):
                yield chunk
            return

        # Legacy fallback
        async for chunk in self._route_stream_legacy(request, trace):
            yield chunk

    # ------------------------------------------------------------------
    # Chain-based routing
    # ------------------------------------------------------------------

    async def _route_with_chain(
        self,
        request: LLMRequest,
        chain: list[RouteOption],
        trace: dict[str, Any] | None,
    ) -> LLMResponse:
        last_exc: Exception | None = None

        for i, opt in enumerate(chain):
            provider = self._providers[opt.provider]
            is_fallback = i > 0

            if trace is not None:
                trace["provider"] = opt.provider
                trace["task"] = request.task.value
                trace["is_fallback"] = is_fallback
                if is_fallback and last_exc:
                    trace["fallback_reason"] = f"{type(last_exc).__name__}: {last_exc}"

            # Inject model override
            request_copy = request.model_copy(update={"model": opt.model})

            start = time.monotonic()
            try:
                response = await provider.generate(request_copy)
                if trace is not None:
                    trace["latency_ms"] = int((time.monotonic() - start) * 1000)
                    trace["model"] = response.model
                    trace["tokens_in"] = response.usage.get("prompt_tokens", 0)
                    trace["tokens_out"] = response.usage.get("completion_tokens", 0)
                    trace["finish_reason"] = response.finish_reason
                if is_fallback:
                    logger.info(
                        "Fallback succeeded: task=%s model=%s (attempt %d/%d)",
                        request.task.value, opt.model, i + 1, len(chain),
                    )
                return response
            except Exception as exc:
                self._rate_tracker.record_error(opt.model, exc)
                last_exc = exc
                logger.warning(
                    "Model %s failed for task=%s (%s): %s — trying next in chain (%d/%d)",
                    opt.model, request.task.value, type(exc).__name__,
                    str(exc)[:200], i + 1, len(chain),
                )

        # All options exhausted
        if trace is not None and last_exc:
            trace["error"] = f"All {len(chain)} fallbacks exhausted. Last: {type(last_exc).__name__}: {last_exc}"
        raise RuntimeError(
            f"All fallback models exhausted for task={request.task.value}"
        ) from last_exc

    async def _route_stream_with_chain(
        self,
        request: LLMRequest,
        chain: list[RouteOption],
        trace: dict[str, Any] | None,
    ) -> AsyncIterator[StreamChunk]:
        last_exc: Exception | None = None

        for i, opt in enumerate(chain):
            provider = self._providers[opt.provider]
            is_fallback = i > 0

            if trace is not None:
                trace["provider"] = opt.provider
                trace["model"] = opt.model
                trace["task"] = request.task.value
                trace["is_fallback"] = is_fallback
                if is_fallback and last_exc:
                    trace["fallback_reason"] = f"{type(last_exc).__name__}: {last_exc}"
                trace["_start"] = time.monotonic()

            request_copy = request.model_copy(update={"model": opt.model})

            try:
                async for chunk in provider.generate_stream(request_copy):
                    yield chunk
                if trace is not None:
                    trace["latency_ms"] = int(
                        (time.monotonic() - trace.pop("_start", 0)) * 1000
                    )
                if is_fallback:
                    logger.info(
                        "Stream fallback succeeded: task=%s model=%s (attempt %d/%d)",
                        request.task.value, opt.model, i + 1, len(chain),
                    )
                return  # success
            except Exception as exc:
                self._rate_tracker.record_error(opt.model, exc)
                last_exc = exc
                logger.warning(
                    "Stream model %s failed for task=%s (%s): %s — trying next (%d/%d)",
                    opt.model, request.task.value, type(exc).__name__,
                    str(exc)[:200], i + 1, len(chain),
                )

        if trace is not None:
            trace.pop("_start", None)
            if last_exc:
                trace["error"] = f"All {len(chain)} fallbacks exhausted"
        raise RuntimeError(
            f"All fallback models exhausted for task={request.task.value}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Legacy routing (no chain — primary + one fallback provider)
    # ------------------------------------------------------------------

    def _get_fallback_named(self, request: LLMRequest) -> tuple[str, LLMProvider] | None:
        primary = self._routing[request.task]
        for fallback_name in ("qwen", "gemini"):
            if fallback_name != primary and fallback_name in self._providers:
                return fallback_name, self._providers[fallback_name]
        return None

    async def _route_legacy(
        self, request: LLMRequest, trace: dict[str, Any] | None
    ) -> LLMResponse:
        provider_name, provider = self._resolve_named(request)
        if trace is not None:
            trace["provider"] = provider_name
            trace["task"] = request.task.value
            trace["is_fallback"] = False
        start = time.monotonic()
        try:
            response = await provider.generate(request)
            if trace is not None:
                trace["latency_ms"] = int((time.monotonic() - start) * 1000)
                trace["model"] = response.model
                trace["tokens_in"] = response.usage.get("prompt_tokens", 0)
                trace["tokens_out"] = response.usage.get("completion_tokens", 0)
                trace["finish_reason"] = response.finish_reason
            return response
        except Exception as exc:
            fb = self._get_fallback_named(request)
            if fb is None:
                if trace is not None:
                    trace["latency_ms"] = int((time.monotonic() - start) * 1000)
                    trace["error"] = f"{type(exc).__name__}: {exc}"
                raise
            fb_name, fallback = fb
            logger.warning(
                "Primary provider failed for task=%s (%s), falling back: %s",
                request.task.value, type(exc).__name__, exc,
            )
            if trace is not None:
                trace["is_fallback"] = True
                trace["fallback_reason"] = f"{type(exc).__name__}: {exc}"
                trace["provider"] = fb_name
            response = await fallback.generate(request)
            if trace is not None:
                trace["latency_ms"] = int((time.monotonic() - start) * 1000)
                trace["model"] = response.model
                trace["tokens_in"] = response.usage.get("prompt_tokens", 0)
                trace["tokens_out"] = response.usage.get("completion_tokens", 0)
                trace["finish_reason"] = response.finish_reason
            return response

    async def _route_stream_legacy(
        self, request: LLMRequest, trace: dict[str, Any] | None
    ) -> AsyncIterator[StreamChunk]:
        provider_name, provider = self._resolve_named(request)
        if trace is not None:
            trace["provider"] = provider_name
            trace["task"] = request.task.value
            trace["is_fallback"] = False
            trace["_start"] = time.monotonic()
        try:
            async for chunk in provider.generate_stream(request):
                yield chunk
            if trace is not None:
                trace["latency_ms"] = int(
                    (time.monotonic() - trace.pop("_start", 0)) * 1000
                )
        except Exception as exc:
            fb = self._get_fallback_named(request)
            if fb is None:
                if trace is not None:
                    trace["latency_ms"] = int(
                        (time.monotonic() - trace.pop("_start", 0)) * 1000
                    )
                    trace["error"] = f"{type(exc).__name__}: {exc}"
                raise
            fb_name, fallback = fb
            logger.warning(
                "Primary provider failed for task=%s (%s), falling back: %s",
                request.task.value, type(exc).__name__, exc,
            )
            if trace is not None:
                trace["is_fallback"] = True
                trace["fallback_reason"] = f"{type(exc).__name__}: {exc}"
                trace["provider"] = fb_name
                trace["_start"] = time.monotonic()
            try:
                async for chunk in fallback.generate_stream(request):
                    yield chunk
            finally:
                if trace is not None:
                    start = trace.pop("_start", 0)
                    trace.setdefault(
                        "latency_ms", int((time.monotonic() - start) * 1000)
                    )
