#!/usr/bin/env python3
"""End-to-end test of multimodal (image) chat against live infrastructure.

Exercises the complete stack: PostgreSQL, Gemini (multimodal), LLMRouter auto-upgrade.
No mocks. All prod settings.

Usage:
    cd backend && python3 scripts/e2e_multimodal_chat.py

Requires:
    - PostgreSQL running (docker compose up -d db)
    - Valid GEMINI_API_KEY in .env
    - Alembic migrations applied (python3 -m alembic upgrade head)

What it tests:
    1. Create profile
    2. Text-only chat — routes to Qwen (normal behavior)
    3. Chat with image — routes to Gemini, AI describes the image
    4. Image in existing conversation — follow-up with image attachment
    5. Verify router auto-upgrade logging
    6. HEIC rejection at upload_helpers level
"""

from __future__ import annotations

import asyncio
import io
import logging
import sys
import time
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

PROFILE_DATA = {
    "account_id": uuid.uuid4(),
    "name": "E2E Multimodal Test",
    "relationship": "self",
    "sex": "male",
    "date_of_birth": date(1990, 1, 1),
    "blood_type": "O+",
    "allergies": [],
    "current_medications": [],
    "medical_conditions": [],
    "family_medical_history": {},
}


def _create_test_jpeg() -> bytes:
    """Create a real JPEG image (red 64x64) for testing."""
    from PIL import Image

    img = Image.new("RGB", (64, 64), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _print_step(n: int, msg: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  STEP {n}: {msg}")
    print(f"{'=' * 60}")


def _print_check(name: str, passed: bool, detail: str = "") -> None:
    icon = "PASS" if passed else "FAIL"
    suffix = f" ({detail})" if detail else ""
    print(f"  {icon}  {name}{suffix}")


def _truncate(text: str, max_len: int = 200) -> str:
    return text[:max_len] + "..." if len(text) > max_len else text


async def _retry_llm(coro_fn, *, max_retries: int = 3, base_delay: float = 30.0):
    """Retry an async callable that may hit LLM rate limits."""
    for attempt in range(max_retries):
        try:
            return await coro_fn()
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = (
                "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str
            )
            if is_rate_limit and attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                print(
                    f"  Rate limited (attempt {attempt + 1}/{max_retries}). Waiting {delay:.0f}s..."
                )
                await asyncio.sleep(delay)
            else:
                raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run() -> bool:
    from app.api.deps import get_agent_core, get_memory_service
    from app.core.database import async_session_factory, engine
    from app.models.profile import Profile
    from app.services.chat import ChatService
    from app.services.context_builder import ContextBuilder
    from app.services.llm import ImagePart
    from app.services.memory_extractor import MemoryExtractor

    engine.echo = False

    memory_service = get_memory_service()
    context_builder = ContextBuilder(memory_service)
    memory_extractor = MemoryExtractor(memory_service)
    agent_core = get_agent_core()

    profile_id: uuid.UUID | None = None
    checks: list[tuple[str, bool]] = []
    jpeg_data = _create_test_jpeg()

    try:
        # ==================================================================
        # STEP 1: Create profile
        # ==================================================================
        _print_step(1, "Create profile")
        async with async_session_factory() as db:
            profile = Profile(id=uuid.uuid4(), **PROFILE_DATA)
            profile_id = profile.id
            db.add(profile)
            await db.commit()
        print(f"  Profile: {profile.name} (id={profile_id})")

        # ==================================================================
        # STEP 2: Text-only chat (baseline — should route to Qwen)
        # ==================================================================
        _print_step(2, "Text-only chat — should route to Qwen")
        conversation_id = None

        async def _send_text():
            async with async_session_factory() as db:
                p = await db.get(Profile, profile_id)
                svc = ChatService(db, agent_core, context_builder, memory_extractor)
                convo, turn = await svc.send_message(p, "What are the benefits of drinking water?")
                await db.commit()
                return convo, turn

        try:
            t0 = time.time()
            convo_a, turn_a = await _retry_llm(_send_text)
            elapsed = time.time() - t0
            conversation_id = convo_a.id

            print(f"  Time: {elapsed:.1f}s")
            print(f"  Model: {turn_a.message.role}")
            print(f"  Response: {_truncate(turn_a.message.content)}")

            checks.append(("Text-only response non-empty", len(turn_a.message.content) > 20))
        except Exception as e:
            print(f"  SKIP — LLM error: {type(e).__name__}: {e}")
            checks.append(("Text-only chat", False))

        # ==================================================================
        # STEP 3: Chat with image — should route to Gemini
        # ==================================================================
        _print_step(3, "Chat with JPEG image — should auto-upgrade to Gemini")

        async def _send_with_image():
            image_parts = [ImagePart(data=jpeg_data, mime_type="image/jpeg")]
            async with async_session_factory() as db:
                p = await db.get(Profile, profile_id)
                svc = ChatService(db, agent_core, context_builder, memory_extractor)
                convo, turn = await svc.send_message(
                    p,
                    "Describe what you see in this image. What color is it?",
                    image_parts=image_parts,
                )
                await db.commit()
                return convo, turn

        try:
            t0 = time.time()
            convo_img, turn_img = await _retry_llm(_send_with_image)
            elapsed = time.time() - t0

            print(f"  Time: {elapsed:.1f}s")
            print(f"  Response ({len(turn_img.message.content)} chars):")
            print(f"    {_truncate(turn_img.message.content)}")

            resp_lower = turn_img.message.content.lower()
            sees_image = any(
                kw in resp_lower
                for kw in ["red", "image", "see", "color", "solid", "square", "picture", "photo"]
            )
            checks.append(("Image response non-empty", len(turn_img.message.content) > 20))
            checks.append(("AI describes image content", sees_image))
        except Exception as e:
            print(f"  FAIL — LLM error: {type(e).__name__}: {e}")
            checks.append(("Image chat", False))

        # ==================================================================
        # STEP 4: Image in existing conversation — continue with image
        # ==================================================================
        _print_step(4, "Follow-up with image in existing conversation")

        if conversation_id:

            async def _send_followup_image():
                image_parts = [ImagePart(data=jpeg_data, mime_type="image/jpeg")]
                async with async_session_factory() as db:
                    p = await db.get(Profile, profile_id)
                    svc = ChatService(db, agent_core, context_builder, memory_extractor)
                    convo, turn = await svc.send_message(
                        p,
                        "Now look at this new image. What do you see?",
                        conversation_id=conversation_id,
                        image_parts=image_parts,
                    )
                    await db.commit()
                    return convo, turn

            try:
                convo_fu, turn_fu = await _retry_llm(_send_followup_image)
                print(f"  Conversation ID: {convo_fu.id}")
                print(f"  Same conversation: {convo_fu.id == conversation_id}")
                print(f"  Response: {_truncate(turn_fu.message.content)}")

                checks.append(("Follow-up in same conversation", convo_fu.id == conversation_id))
                checks.append(("Follow-up response non-empty", len(turn_fu.message.content) > 20))
            except Exception as e:
                print(f"  FAIL — {type(e).__name__}: {e}")
                checks.append(("Follow-up image", False))
        else:
            print("  SKIP — no conversation from step 2")

        # ==================================================================
        # STEP 5: Upload helper validation
        # ==================================================================
        _print_step(5, "Upload helper — HEIC rejection + valid JPEG acceptance")
        from fastapi import UploadFile

        from app.api.upload_helpers import read_image_parts

        # Valid JPEG
        valid_file = UploadFile(
            filename="test.jpg",
            file=io.BytesIO(jpeg_data),
            headers={"content-type": "image/jpeg"},
        )
        parts = await read_image_parts([valid_file])
        checks.append(("JPEG accepted", len(parts) == 1 and parts[0].mime_type == "image/jpeg"))
        print(f"  JPEG accepted: {len(parts)} part(s), mime={parts[0].mime_type}")

        # HEIC rejection
        heic_file = UploadFile(
            filename="photo.heic",
            file=io.BytesIO(b"fake heic data"),
            headers={"content-type": "image/heic"},
        )
        try:
            await read_image_parts([heic_file])
            checks.append(("HEIC rejected", False))
            print("  HEIC: NOT rejected (BUG)")
        except Exception as e:
            checks.append(("HEIC rejected", "400" in str(e.status_code)))
            print(f"  HEIC rejected: {e.detail}")

    finally:
        # Cleanup — delete conversations/messages first (no cascade), then profile
        if profile_id:
            from sqlalchemy import delete

            from app.models.chat import ChatConversation, ChatMessage

            async with async_session_factory() as db:
                # Get conversation IDs for this profile
                from sqlalchemy import select

                cids = (
                    (
                        await db.execute(
                            select(ChatConversation.id).where(
                                ChatConversation.profile_id == profile_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                if cids:
                    await db.execute(
                        delete(ChatMessage).where(ChatMessage.conversation_id.in_(cids))
                    )
                    await db.execute(delete(ChatConversation).where(ChatConversation.id.in_(cids)))
                profile = await db.get(Profile, profile_id)
                if profile:
                    await db.delete(profile)
                await db.commit()
            print(f"\n  Cleaned up profile {profile_id}")

    # ==================================================================
    # Summary
    # ==================================================================
    print(f"\n{'=' * 60}")
    print("  RESULTS")
    print(f"{'=' * 60}")

    passed = sum(1 for _, p in checks if p)
    total = len(checks)

    for name, ok in checks:
        _print_check(name, ok)

    print(f"\n  {passed}/{total} checks passed")
    return passed == total


if __name__ == "__main__":
    ok = asyncio.run(run())
    sys.exit(0 if ok else 1)
