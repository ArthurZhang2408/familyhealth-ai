from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm import LLMMessage, LLMProvider, LLMRequest, LLMResponse, LLMRouter, LLMTask

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_router(
    gemini: LLMProvider | None = None,
    qwen: LLMProvider | None = None,
) -> LLMRouter:
    providers: dict[str, LLMProvider] = {}
    if gemini is not None:
        providers["gemini"] = gemini
    if qwen is not None:
        providers["qwen"] = qwen
    return LLMRouter(providers)


def _make_request(task: LLMTask) -> LLMRequest:
    return LLMRequest(
        task=task,
        system_prompt="You are a helpful assistant.",
        messages=[LLMMessage(role="user", content="Hello")],
    )


# ── Router tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_router_routes_diagnosis_to_gemini() -> None:
    gemini = AsyncMock(spec=LLMProvider)
    gemini.generate.return_value = LLMResponse(content="ok", model="gemini-2.5-flash", usage={})
    qwen = AsyncMock(spec=LLMProvider)

    router = _make_router(gemini=gemini, qwen=qwen)
    await router.route(_make_request(LLMTask.DIAGNOSIS))

    gemini.generate.assert_awaited_once()
    qwen.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_llm_router_routes_chat_to_gemini_by_default() -> None:
    gemini = AsyncMock(spec=LLMProvider)
    gemini.generate.return_value = LLMResponse(content="hi", model="gemini-2.5-flash-lite", usage={})
    qwen = AsyncMock(spec=LLMProvider)

    router = _make_router(gemini=gemini, qwen=qwen)
    await router.route(_make_request(LLMTask.CHAT))

    gemini.generate.assert_awaited_once()
    qwen.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_llm_router_env_override_routes_chat_to_qwen() -> None:
    gemini = AsyncMock(spec=LLMProvider)
    qwen = AsyncMock(spec=LLMProvider)
    qwen.generate.return_value = LLMResponse(content="hi", model="qwen3.5:397b", usage={})

    router = LLMRouter(
        {"gemini": gemini, "qwen": qwen},
        route_overrides={LLMTask.CHAT: "qwen"},
    )
    await router.route(_make_request(LLMTask.CHAT))

    qwen.generate.assert_awaited_once()
    gemini.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_llm_router_missing_provider_raises() -> None:
    router = LLMRouter({})
    with pytest.raises(ValueError, match="No provider registered"):
        await router.route(_make_request(LLMTask.DIAGNOSIS))


# ── GeminiProvider tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.llm_gemini.genai.Client")
async def test_gemini_provider_generate(mock_client_cls: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.text = "Test response"
    mock_response.usage_metadata.prompt_token_count = 10
    mock_response.usage_metadata.candidates_token_count = 20

    mock_aio = AsyncMock()
    mock_aio.generate_content.return_value = mock_response
    mock_client = MagicMock()
    mock_client.aio.models = mock_aio
    mock_client_cls.return_value = mock_client

    from app.services.llm_gemini import GeminiProvider

    provider = GeminiProvider(api_key="test-key")
    request = LLMRequest(
        task=LLMTask.DIAGNOSIS,
        system_prompt="You are a doctor.",
        messages=[LLMMessage(role="user", content="I have a headache")],
    )
    result = await provider.generate(request)

    assert isinstance(result, LLMResponse)
    assert result.content == "Test response"
    assert result.model == "gemini-2.5-flash"  # DIAGNOSIS uses diagnosis model
    assert result.usage["prompt_tokens"] == 10
    assert result.usage["completion_tokens"] == 20


def test_gemini_provider_model_selection() -> None:
    from app.services.llm_gemini import GeminiProvider

    provider = GeminiProvider.__new__(GeminiProvider)
    provider._diagnosis_model = "gemini-2.5-flash"
    provider._report_model = "gemini-2.5-flash"
    provider._default_model = "gemini-2.5-flash-lite"

    assert provider._select_model(LLMTask.DIAGNOSIS) == "gemini-2.5-flash"
    assert provider._select_model(LLMTask.REPORT_ANALYSIS) == "gemini-2.5-flash"
    assert provider._select_model(LLMTask.CHAT) == "gemini-2.5-flash-lite"
    assert provider._select_model(LLMTask.TOPIC_GENERATION) == "gemini-2.5-flash-lite"


# ── QwenProvider tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.llm_qwen.openai.AsyncOpenAI")
async def test_qwen_provider_generate(mock_client_cls: MagicMock) -> None:
    mock_choice = MagicMock()
    mock_choice.message.content = "Qwen response"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "qwen3.5:397b"
    mock_response.usage.prompt_tokens = 15
    mock_response.usage.completion_tokens = 25

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    mock_client_cls.return_value = mock_client

    from app.services.llm_qwen import QwenProvider

    provider = QwenProvider(api_key="test-key")
    request = LLMRequest(
        task=LLMTask.CHAT,
        system_prompt="You are a health assistant.",
        messages=[LLMMessage(role="user", content="Hello")],
    )
    result = await provider.generate(request)

    assert isinstance(result, LLMResponse)
    assert result.content == "Qwen response"
    assert result.model == "qwen3.5:397b"
    assert result.usage["prompt_tokens"] == 15
    assert result.usage["completion_tokens"] == 25


# ── LLMRequest defaults ────────────────────────────────────────────────────


def test_llm_request_defaults() -> None:
    req = LLMRequest(
        task=LLMTask.CHAT,
        system_prompt="sys",
        messages=[LLMMessage(role="user", content="hi")],
    )
    assert req.temperature == 0.7
    assert req.max_tokens is None
    assert req.response_format is None
