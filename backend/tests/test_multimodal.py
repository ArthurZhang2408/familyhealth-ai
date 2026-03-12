"""End-to-end tests for multimodal (image) support in chat and diagnosis.

Tests cover:
- Sending images via multipart FormData to chat and diagnosis endpoints
- HEIC/unsupported MIME type rejection at the API layer
- Oversized file rejection
- Router auto-upgrade from Qwen → Gemini when images are present
- Text-only messages still route to Qwen (no regression)
- upload_helpers.read_image_parts() edge cases
- Gemini model selection upgrade for image requests
"""

from __future__ import annotations

import io
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.agents.core import AgentCore
from app.agents.registry import ToolRegistry
from app.api.deps import get_agent_core, get_context_builder, get_memory_extractor
from app.api.upload_helpers import read_image_parts
from app.main import app
from app.services.llm import ImagePart, LLMMessage, LLMRequest, LLMRouter, LLMTask

from .conftest import TEST_ACCOUNT_ID

# ---------------------------------------------------------------------------
# Test image fixtures
# ---------------------------------------------------------------------------


# Generate minimal valid test images at import time
def _make_tiny_jpeg() -> bytes:
    """Create a minimal 1x1 JPEG in memory."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(buf, format="JPEG")
    return buf.getvalue()


def _make_tiny_png() -> bytes:
    """Create a minimal 1x1 PNG in memory."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


TINY_JPEG = _make_tiny_jpeg()
TINY_PNG = _make_tiny_png()


def _make_jpeg_file(
    name: str = "test.jpg", size: int | None = None
) -> tuple[str, io.BytesIO, str]:
    """Create an (name, file, content_type) tuple for httpx multipart upload."""
    data = TINY_JPEG if size is None else (b"\xff\xd8\xff\xe0" + b"\x00" * size)
    buf = io.BytesIO(data)
    buf.name = name
    return (name, buf, "image/jpeg")


def _make_png_file(name: str = "test.png") -> tuple[str, io.BytesIO, str]:
    buf = io.BytesIO(TINY_PNG)
    buf.name = name
    return (name, buf, "image/png")


# ---------------------------------------------------------------------------
# Mock helpers (same pattern as test_chat_service.py)
# ---------------------------------------------------------------------------

MOCK_IMAGE_RESPONSE = (
    "I can see the image you've shared. It appears to show a skin condition. "
    "Based on the visual appearance, it could be a minor rash. However, I'd "
    "recommend consulting a dermatologist for a proper diagnosis."
)


def _mock_llm_router_with_image_tracking() -> MagicMock:
    """Mock router that records whether images were received across all calls.

    Tracks per-call history so the topic-generation pass (summarization)
    doesn't overwrite the chat pass results.
    """
    router = AsyncMock()
    router._calls: list[dict] = []

    async def mock_route(request: Any, **kwargs: Any) -> MagicMock:
        has_images = any(m.image_parts for m in request.messages if m.image_parts)
        provider = "gemini" if has_images else "qwen"
        router._calls.append(
            {
                "task": str(request.task),
                "has_images": has_images,
                "provider": provider,
            }
        )

        resp = MagicMock()
        resp.content = MOCK_IMAGE_RESPONSE if has_images else "Text-only response"
        resp.model = "gemini-2.5-flash" if has_images else "qwen3.5:397b"
        resp.usage = {"prompt_tokens": 100, "completion_tokens": 50}
        resp.finish_reason = "stop"
        resp.tool_calls = None
        return resp

    router.route = mock_route

    # Convenience: check if ANY call received images
    @property  # type: ignore[misc]
    def _received_images(self: Any) -> bool:
        return any(c["has_images"] for c in self._calls)

    @property  # type: ignore[misc]
    def _provider_used(self: Any) -> str | None:
        """Provider used for the primary (non-summarization) call."""
        for c in self._calls:
            if c["task"] != "summarization":
                return c["provider"]
        return self._calls[0]["provider"] if self._calls else None

    type(router)._received_images = _received_images
    type(router)._provider_used = _provider_used
    return router


def _mock_context_builder() -> MagicMock:
    builder = AsyncMock()
    ctx = MagicMock()
    ctx.system_prompt = "mock system prompt"
    ctx.profile_context = {"name": "Test Patient"}
    ctx.memories_used = 0
    ctx.token_counts = {"profile": 50, "memories": 0, "total": 100}
    builder.build = AsyncMock(return_value=ctx)
    return builder


def _mock_memory_extractor() -> MagicMock:
    extractor = AsyncMock()
    extractor.extract_and_store = AsyncMock(return_value=None)
    return extractor


def _override_deps_with_router(router: MagicMock) -> None:
    app.dependency_overrides[get_agent_core] = lambda: AgentCore(
        llm_router=router, tool_registry=ToolRegistry()
    )
    app.dependency_overrides[get_context_builder] = _mock_context_builder
    app.dependency_overrides[get_memory_extractor] = _mock_memory_extractor


async def _create_profile(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/profiles",
        json={"name": "Multimodal Test User", "relationship": "self"},
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Unit Tests — upload_helpers.py
# ---------------------------------------------------------------------------


class TestUploadHelpers:
    @pytest.mark.asyncio
    async def test_read_image_parts_jpeg(self) -> None:
        from fastapi import UploadFile

        file = UploadFile(
            filename="test.jpg", file=io.BytesIO(TINY_JPEG), headers={"content-type": "image/jpeg"}
        )
        parts = await read_image_parts([file])
        assert len(parts) == 1
        assert parts[0].mime_type == "image/jpeg"
        assert parts[0].data == TINY_JPEG

    @pytest.mark.asyncio
    async def test_read_image_parts_empty_list(self) -> None:
        parts = await read_image_parts([])
        assert parts == []

    @pytest.mark.asyncio
    async def test_read_image_parts_rejects_heic(self) -> None:
        from fastapi import HTTPException, UploadFile

        file = UploadFile(
            filename="photo.heic", file=io.BytesIO(b"fake"), headers={"content-type": "image/heic"}
        )
        with pytest.raises(HTTPException) as exc_info:
            await read_image_parts([file])
        assert exc_info.value.status_code == 400
        assert "image/heic" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_read_image_parts_rejects_oversized(self) -> None:
        from fastapi import HTTPException, UploadFile

        big_data = b"\x00" * (11 * 1024 * 1024)  # 11 MB
        file = UploadFile(
            filename="big.jpg", file=io.BytesIO(big_data), headers={"content-type": "image/jpeg"}
        )
        with pytest.raises(HTTPException) as exc_info:
            await read_image_parts([file])
        assert exc_info.value.status_code == 400
        assert "too large" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_read_image_parts_pdf(self) -> None:
        from fastapi import UploadFile

        pdf_data = b"%PDF-1.4 fake pdf"
        file = UploadFile(
            filename="report.pdf",
            file=io.BytesIO(pdf_data),
            headers={"content-type": "application/pdf"},
        )
        parts = await read_image_parts([file])
        assert len(parts) == 1
        assert parts[0].mime_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_read_image_parts_rejects_too_many_files(self) -> None:
        from fastapi import HTTPException, UploadFile

        files = [
            UploadFile(
                filename=f"img{i}.jpg",
                file=io.BytesIO(TINY_JPEG),
                headers={"content-type": "image/jpeg"},
            )
            for i in range(6)
        ]
        with pytest.raises(HTTPException) as exc_info:
            await read_image_parts(files)
        assert exc_info.value.status_code == 400
        assert "too many" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_read_image_parts_multiple_files(self) -> None:
        from fastapi import UploadFile

        files = [
            UploadFile(
                filename="a.jpg",
                file=io.BytesIO(TINY_JPEG),
                headers={"content-type": "image/jpeg"},
            ),
            UploadFile(
                filename="b.png", file=io.BytesIO(TINY_PNG), headers={"content-type": "image/png"}
            ),
        ]
        parts = await read_image_parts(files)
        assert len(parts) == 2
        assert parts[0].mime_type == "image/jpeg"
        assert parts[1].mime_type == "image/png"


# ---------------------------------------------------------------------------
# Unit Tests — LLMRouter auto-upgrade
# ---------------------------------------------------------------------------


class TestRouterAutoUpgrade:
    def _make_router(self) -> LLMRouter:
        gemini = AsyncMock()
        gemini.generate = AsyncMock(return_value=MagicMock(content="gemini response"))
        qwen = AsyncMock()
        qwen.generate = AsyncMock(return_value=MagicMock(content="qwen response"))
        return LLMRouter(providers={"gemini": gemini, "qwen": qwen})

    def test_text_only_chat_routes_to_qwen(self) -> None:
        router = self._make_router()
        request = LLMRequest(
            task=LLMTask.CHAT,
            system_prompt="test",
            messages=[LLMMessage(role="user", content="hello")],
        )
        provider = router._resolve(request)
        assert provider == router._providers["qwen"]

    def test_chat_with_image_routes_to_gemini(self) -> None:
        router = self._make_router()
        request = LLMRequest(
            task=LLMTask.CHAT,
            system_prompt="test",
            messages=[
                LLMMessage(
                    role="user",
                    content="look at this",
                    image_parts=[ImagePart(data=TINY_JPEG, mime_type="image/jpeg")],
                ),
            ],
        )
        provider = router._resolve(request)
        assert provider == router._providers["gemini"]

    def test_diagnosis_always_routes_to_gemini(self) -> None:
        router = self._make_router()
        request = LLMRequest(
            task=LLMTask.DIAGNOSIS,
            system_prompt="test",
            messages=[LLMMessage(role="user", content="I have a cough")],
        )
        provider = router._resolve(request)
        assert provider == router._providers["gemini"]

    def test_image_in_history_triggers_upgrade(self) -> None:
        """Even if the image is in an earlier message (not the latest), still upgrade."""
        router = self._make_router()
        request = LLMRequest(
            task=LLMTask.CHAT,
            system_prompt="test",
            messages=[
                LLMMessage(
                    role="user",
                    content="look at this rash",
                    image_parts=[ImagePart(data=TINY_JPEG, mime_type="image/jpeg")],
                ),
                LLMMessage(role="assistant", content="I see a rash"),
                LLMMessage(role="user", content="is it serious?"),
            ],
        )
        provider = router._resolve(request)
        assert provider == router._providers["gemini"]


# ---------------------------------------------------------------------------
# Unit Tests — Gemini model selection with images
# ---------------------------------------------------------------------------


class TestGeminiModelSelection:
    def test_chat_without_images_uses_default(self) -> None:
        from app.services.llm_gemini import GeminiProvider

        provider = GeminiProvider.__new__(GeminiProvider)
        provider._diagnosis_model = "gemini-2.5-flash"
        provider._report_model = "gemini-2.5-flash"
        provider._default_model = "gemini-2.5-flash-lite"

        assert provider._select_model(LLMTask.CHAT, has_images=False) == "gemini-2.5-flash-lite"

    def test_chat_with_images_uses_default_model(self) -> None:
        """Flash Lite supports multimodal — no upgrade needed for chat images."""
        from app.services.llm_gemini import GeminiProvider

        provider = GeminiProvider.__new__(GeminiProvider)
        provider._diagnosis_model = "gemini-2.5-flash"
        provider._report_model = "gemini-2.5-flash"
        provider._default_model = "gemini-2.5-flash-lite"

        assert provider._select_model(LLMTask.CHAT, has_images=True) == "gemini-2.5-flash-lite"

    def test_diagnosis_always_uses_diagnosis_model(self) -> None:
        from app.services.llm_gemini import GeminiProvider

        provider = GeminiProvider.__new__(GeminiProvider)
        provider._diagnosis_model = "gemini-2.5-flash"
        provider._report_model = "gemini-2.5-flash"
        provider._default_model = "gemini-2.5-flash-lite"

        assert provider._select_model(LLMTask.DIAGNOSIS, has_images=False) == "gemini-2.5-flash"
        assert provider._select_model(LLMTask.DIAGNOSIS, has_images=True) == "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# E2E Route Tests — Chat with images
# ---------------------------------------------------------------------------


class TestChatMultimodal:
    @pytest.mark.asyncio
    async def test_send_image_in_chat(self, client: AsyncClient) -> None:
        """Send a JPEG image with text via multipart — should get AI response about the image."""
        router = _mock_llm_router_with_image_tracking()
        _override_deps_with_router(router)
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "What does this rash look like?"},
            files=[("files", _make_jpeg_file())],
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["message"]["role"] == "assistant"
        assert router._received_images is True
        assert router._provider_used == "gemini"

    @pytest.mark.asyncio
    async def test_send_image_only_no_text(self, client: AsyncClient) -> None:
        """Send an image with minimal text content."""
        router = _mock_llm_router_with_image_tracking()
        _override_deps_with_router(router)
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "Please look at this image."},
            files=[("files", _make_png_file())],
        )
        assert resp.status_code == 201
        assert router._received_images is True

    @pytest.mark.asyncio
    async def test_text_only_still_works(self, client: AsyncClient) -> None:
        """Text-only chat should still route to Qwen (no regression)."""
        router = _mock_llm_router_with_image_tracking()
        _override_deps_with_router(router)
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "How much water should I drink?"},
        )
        assert resp.status_code == 201
        assert router._received_images is False
        assert router._provider_used == "qwen"

    @pytest.mark.asyncio
    async def test_reject_unsupported_mime_type(self, client: AsyncClient) -> None:
        """HEIC and other unsupported types should be rejected."""
        router = _mock_llm_router_with_image_tracking()
        _override_deps_with_router(router)
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "Look at this"},
            files=[("files", ("photo.heic", io.BytesIO(b"fake heic data"), "image/heic"))],
        )
        assert resp.status_code == 400
        assert "image/heic" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_reject_oversized_file(self, client: AsyncClient) -> None:
        """Files over 10 MB should be rejected."""
        router = _mock_llm_router_with_image_tracking()
        _override_deps_with_router(router)
        profile = await _create_profile(client)
        pid = profile["id"]

        big_data = b"\xff\xd8\xff\xe0" + b"\x00" * (11 * 1024 * 1024)
        resp = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "Big file"},
            files=[("files", ("big.jpg", io.BytesIO(big_data), "image/jpeg"))],
        )
        assert resp.status_code == 400
        assert "too large" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_multiple_images(self, client: AsyncClient) -> None:
        """Multiple images in one message should all be received."""
        router = _mock_llm_router_with_image_tracking()
        _override_deps_with_router(router)
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "Compare these two"},
            files=[
                ("files", _make_jpeg_file("a.jpg")),
                ("files", _make_png_file("b.png")),
            ],
        )
        assert resp.status_code == 201
        assert router._received_images is True

    @pytest.mark.asyncio
    async def test_continue_conversation_with_image(self, client: AsyncClient) -> None:
        """Send text first, then follow up with an image in the same conversation."""
        router = _mock_llm_router_with_image_tracking()
        _override_deps_with_router(router)
        profile = await _create_profile(client)
        pid = profile["id"]

        # First: text-only
        resp1 = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "I have a rash on my arm"},
        )
        assert resp1.status_code == 201
        cid = resp1.json()["message"]["conversation_id"]
        calls_before = len(router._calls)

        # Second: image in same conversation
        resp2 = await client.post(
            f"/api/v1/profiles/{pid}/chat",
            data={"content": "Here's a photo", "conversation_id": cid},
            files=[("files", _make_jpeg_file())],
        )
        assert resp2.status_code == 201
        assert resp2.json()["message"]["conversation_id"] == cid

        # Find the chat call from the second request (skip summarization calls)
        new_calls = [c for c in router._calls[calls_before:] if c["task"] == "chat"]
        assert len(new_calls) == 1
        assert new_calls[0]["has_images"] is True
        assert new_calls[0]["provider"] == "gemini"


# ---------------------------------------------------------------------------
# E2E Route Tests — Diagnosis with images
# ---------------------------------------------------------------------------


class TestDiagnosisMultimodal:
    @pytest.mark.asyncio
    async def test_send_image_in_diagnosis(self, client: AsyncClient) -> None:
        """Send an image during a diagnosis session."""
        router = _mock_llm_router_with_image_tracking()
        _override_deps_with_router(router)
        profile = await _create_profile(client)
        pid = profile["id"]

        # Create diagnosis session
        create_resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "I have a wound on my leg"},
        )
        assert create_resp.status_code == 201
        sid = create_resp.json()["message"]["session_id"]
        calls_before = len(router._calls)

        # Send image in diagnosis
        resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis/{sid}/messages",
            data={"content": "Here is a photo of the wound"},
            files=[("files", _make_jpeg_file())],
        )
        assert resp.status_code == 201
        assert resp.json()["message"]["role"] == "assistant"

        # The diagnosis call with images should route to gemini
        dx_calls = [c for c in router._calls[calls_before:] if c["task"] == "diagnosis"]
        assert len(dx_calls) >= 1
        assert dx_calls[0]["has_images"] is True
        assert dx_calls[0]["provider"] == "gemini"

    @pytest.mark.asyncio
    async def test_diagnosis_text_only_no_regression(self, client: AsyncClient) -> None:
        """Text-only diagnosis messages should still work normally."""
        router = _mock_llm_router_with_image_tracking()
        _override_deps_with_router(router)
        profile = await _create_profile(client)
        pid = profile["id"]

        create_resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis",
            json={"chief_complaint": "Persistent cough"},
        )
        assert create_resp.status_code == 201
        sid = create_resp.json()["message"]["session_id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/diagnosis/{sid}/messages",
            data={"content": "The cough started 5 days ago"},
        )
        assert resp.status_code == 201
        # Diagnosis normally routes to Gemini anyway
        assert router._received_images is False
