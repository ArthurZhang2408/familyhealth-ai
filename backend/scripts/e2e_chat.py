#!/usr/bin/env python3
"""End-to-end test of the chat feature against live infrastructure.

Exercises the complete stack: PostgreSQL, Mem0, Qwen (chat + topic generation).
No mocks. All prod settings.

Usage:
    cd backend && python3 scripts/e2e_chat.py

Requires:
    - PostgreSQL running (docker compose up -d db)
    - Valid GEMINI_API_KEY and QWEN_API_KEY in .env
    - Alembic migrations applied (python3 -m alembic upgrade head)

What it tests:
    1.  Profile creation with rich medical data
    2.  Memory seeding via Mem0
    3.  Basic chat: Qwen responds to a health question
    4.  Profile-aware response: LLM references the patient's conditions/medications
    5.  Topic auto-generation: short label produced from first message
    6.  Messages persisted in DB
    7.  Action log entry created
    8.  Memory extraction: facts stored in Mem0 after conversation
    9.  Multi-turn continuity: second message in same conversation gets context
    10. Mental health crisis: instant response (<1s), crisis resources present
    11. Memory retrieval: seeded + extracted memories are searchable
    12. Conversation listing and get
"""

from __future__ import annotations

import asyncio
import json
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
    "name": "Chen Wei",
    "relationship": "parent",
    "sex": "female",
    "date_of_birth": date(1964, 3, 15),
    "blood_type": "A+",
    "allergies": [
        {"allergen": "Penicillin", "severity": "severe", "reaction": "anaphylaxis risk"},
        {"allergen": "Shellfish", "severity": "mild", "reaction": "hives"},
    ],
    "current_medications": [
        {"name": "Metformin", "dosage": "1000mg", "frequency": "twice daily"},
        {"name": "Lisinopril", "dosage": "10mg", "frequency": "once daily"},
    ],
    "medical_conditions": [
        {"condition": "Type 2 Diabetes", "diagnosed": "2019", "status": "active"},
        {"condition": "Hypertension", "diagnosed": "2020", "status": "managed"},
    ],
    "family_medical_history": {
        "Heart Disease": ["Father (heart attack at 55)"],
        "Diabetes": ["Maternal grandmother"],
    },
}

# Seed conversations to pre-populate Mem0 with episodic history
SEED_CONVERSATIONS = [
    {
        "messages": [
            {
                "role": "user",
                "content": (
                    "Mom's latest HbA1c was 7.8%. The doctor said blood sugar "
                    "control has gotten worse and wants to add a second medication."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "An HbA1c of 7.8% indicates suboptimal glycemic control. "
                    "Adding a second medication like a GLP-1 agonist is reasonable."
                ),
            },
        ],
        "category": "lab_results",
        "source": "chat:e2e-seed-1",
    },
    {
        "messages": [
            {
                "role": "user",
                "content": (
                    "She's been having trouble sleeping — wakes up 2-3 times a night "
                    "and can't fall back asleep. It's been going on for 6 weeks."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Chronic insomnia lasting 6+ weeks warrants attention. For someone "
                    "with hypertension and diabetes, poor sleep can worsen both conditions."
                ),
            },
        ],
        "category": "symptoms",
        "source": "chat:e2e-seed-2",
    },
]

# Scenario A: Basic health question (no prior context needed)
QUESTION_BASIC = "What are some practical tips for managing blood sugar levels throughout the day?"

# Scenario B: Profile-aware question — should trigger mention of Metformin/diabetes
QUESTION_PROFILE_AWARE = (
    "Mom has been feeling more tired than usual since her last medication adjustment. "
    "Could it be related to her diabetes management?"
)

# Scenario C: Second turn in same conversation (multi-turn continuity)
QUESTION_FOLLOWUP = (
    "She also mentioned that the fatigue gets worse after meals. " "Does that change anything?"
)

# Scenario D: Mental health crisis
CRISIS_MESSAGE = "I feel like there's no reason to live anymore"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_step(n: int, msg: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  STEP {n}: {msg}")
    print(f"{'=' * 60}")


def _print_check(name: str, passed: bool, detail: str = "") -> None:
    icon = "PASS" if passed else "FAIL"
    suffix = f" ({detail})" if detail else ""
    print(f"  {icon}  {name}{suffix}")


def _truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


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
                    f"  Rate limited (attempt {attempt + 1}/{max_retries}). "
                    f"Waiting {delay:.0f}s..."
                )
                await asyncio.sleep(delay)
            else:
                raise


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------


async def run() -> bool:
    from sqlalchemy import select

    from app.api.deps import get_agent_core, get_memory_service
    from app.core.database import async_session_factory, engine
    from app.models.action_log import ActionLog
    from app.models.chat import ChatConversation, ChatMessage
    from app.models.profile import Profile
    from app.services.chat import ChatService
    from app.services.chat_prompts import CHAT_DISCLAIMER
    from app.services.context_builder import ContextBuilder
    from app.services.memory_extractor import MemoryExtractor

    engine.echo = False

    memory_service = get_memory_service()
    context_builder = ContextBuilder(memory_service)
    memory_extractor = MemoryExtractor(memory_service)
    agent_core = get_agent_core()

    profile_id: uuid.UUID | None = None
    checks: list[tuple[str, bool]] = []
    llm_available = True

    try:
        # ==================================================================
        # STEP 1: Create profile
        # ==================================================================
        _print_step(1, "Create profile with rich medical data")
        async with async_session_factory() as db:
            profile = Profile(id=uuid.uuid4(), **PROFILE_DATA)
            profile_id = profile.id
            db.add(profile)
            await db.commit()
        print(f"  Profile: {profile.name} (id={profile_id})")
        conditions = ", ".join(c["condition"] for c in PROFILE_DATA["medical_conditions"])
        print(f"  Conditions: {conditions}")
        print(
            f"  Medications: {', '.join(m['name'] for m in PROFILE_DATA['current_medications'])}"
        )

        # ==================================================================
        # STEP 2: Seed episodic memories via Mem0
        # ==================================================================
        _print_step(2, "Seed episodic memories via Mem0")
        total_facts = 0
        for conv in SEED_CONVERSATIONS:
            result = await memory_service.add(
                profile_id,
                conv["messages"],
                category=conv["category"],
                source=conv["source"],
            )
            facts = result.get("results", [])
            total_facts += len(facts)
            for f in facts:
                print(f"  [{f.get('event')}] {f.get('memory', '')}")
        print(f"  Total facts extracted: {total_facts}")
        checks.append(("Mem0 seed extraction", total_facts > 0))

        # ==================================================================
        # STEP 3: Basic chat — first message creates conversation
        # ==================================================================
        _print_step(3, "Basic chat — first message, Qwen responds")
        t0 = time.time()
        conversation_id: uuid.UUID | None = None
        turn_a = None

        async def _send_basic():
            async with async_session_factory() as db:
                lp = await db.get(Profile, profile_id)
                svc = ChatService(db, agent_core, context_builder, memory_extractor)
                convo, trn = await svc.send_message(lp, QUESTION_BASIC)
                await db.commit()
                return convo, trn

        try:
            convo_a, turn_a = await _retry_llm(_send_basic)
            conversation_id = convo_a.id
            elapsed = time.time() - t0

            print(f"  Conversation ID: {conversation_id}")
            print(f"  Time: {elapsed:.1f}s")
            print(f"  Topic: {convo_a.topic!r}")
            print(f"  Response ({len(turn_a.message.content)} chars):")
            print(f"    {_truncate(turn_a.message.content, 200)}")

            checks.append(("Response non-empty", len(turn_a.message.content) > 50))
            checks.append(("Disclaimer present", turn_a.disclaimer == CHAT_DISCLAIMER))
            checks.append(
                (
                    "Response is health-relevant",
                    any(
                        kw in turn_a.message.content.lower()
                        for kw in [
                            "blood sugar",
                            "glucose",
                            "diabetes",
                            "diet",
                            "carbohydrate",
                            "insulin",
                            "meal",
                        ]
                    ),
                )
            )

        except Exception as e:
            llm_available = False
            print(f"  SKIP — LLM unavailable: {type(e).__name__}: {e}")
            checks.append(("Response non-empty [LLM]", False))

        # ==================================================================
        # STEP 4: Topic auto-generated
        # ==================================================================
        _print_step(4, "Verify topic auto-generated for new conversation")

        if llm_available and conversation_id:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(ChatConversation).where(ChatConversation.id == conversation_id)
                )
                convo_db = result.scalar_one_or_none()

            topic = convo_db.topic if convo_db else None
            print(f"  Topic: {topic!r}")
            checks.append(("Topic auto-generated", topic is not None and len(topic) > 0))
            checks.append(
                ("Topic is concise (<= 60 chars)", topic is not None and len(topic) <= 60)
            )
        else:
            print("  SKIP — no conversation created")

        # ==================================================================
        # STEP 5: Profile-aware response
        # ==================================================================
        _print_step(5, "Profile-aware response — LLM references patient's conditions")
        turn_b = None

        async def _send_profile_aware():
            async with async_session_factory() as db:
                lp = await db.get(Profile, profile_id)
                svc = ChatService(db, agent_core, context_builder, memory_extractor)
                convo, trn = await svc.send_message(lp, QUESTION_PROFILE_AWARE)
                await db.commit()
                return convo, trn

        if llm_available:
            try:
                convo_b, turn_b = await _retry_llm(_send_profile_aware)
                print(f"  Response ({len(turn_b.message.content)} chars):")
                print(f"    {_truncate(turn_b.message.content, 200)}")

                # The response should reference diabetes/medications
                resp_lower = turn_b.message.content.lower()
                profile_refs = sum(
                    [
                        "diabetes" in resp_lower,
                        "metformin" in resp_lower,
                        "blood sugar" in resp_lower,
                        "glucose" in resp_lower,
                        "fatigue" in resp_lower or "tired" in resp_lower,
                    ]
                )
                print(f"  Profile-aware signals: {profile_refs}/5")
                checks.append(("Profile-aware (mentions patient context)", profile_refs >= 2))

            except Exception as e:
                print(f"  SKIP — LLM error: {type(e).__name__}")
        else:
            print("  SKIP — LLM unavailable")

        # ==================================================================
        # STEP 6: Multi-turn continuity — second message in same conversation
        # ==================================================================
        _print_step(6, "Multi-turn continuity — continue conversation with conversation_id")

        if llm_available and conversation_id:

            async def _send_followup():
                async with async_session_factory() as db:
                    lp = await db.get(Profile, profile_id)
                    svc = ChatService(db, agent_core, context_builder, memory_extractor)
                    convo, trn = await svc.send_message(
                        lp, QUESTION_FOLLOWUP, conversation_id=conversation_id
                    )
                    await db.commit()
                    return convo, trn

            try:
                convo_c, turn_c = await _retry_llm(_send_followup)
                print(f"  Response ({len(turn_c.message.content)} chars):")
                print(f"    {_truncate(turn_c.message.content, 200)}")

                checks.append(
                    (
                        "Followup in same conversation",
                        convo_c.id == conversation_id,
                    )
                )
                checks.append(("Followup response non-empty", len(turn_c.message.content) > 30))

            except Exception as e:
                print(f"  SKIP — LLM error: {type(e).__name__}")
        else:
            print("  SKIP — LLM unavailable or no conversation")

        # ==================================================================
        # STEP 7: Verify messages stored in DB
        # ==================================================================
        _print_step(7, "Verify messages persisted in database")

        if llm_available and conversation_id:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(ChatMessage)
                    .where(ChatMessage.conversation_id == conversation_id)
                    .order_by(ChatMessage.created_at)
                )
                messages = result.scalars().all()

            user_msgs = [m for m in messages if m.role == "user"]
            asst_msgs = [m for m in messages if m.role == "assistant"]
            # Basic message + followup = 2 user + 2 assistant = 4 total
            print(f"  Total messages: {len(messages)}")
            print(f"  User: {len(user_msgs)}, Assistant: {len(asst_msgs)}")
            for m in messages:
                print(f"    [{m.role}] {_truncate(m.content, 80)}")

            checks.append(("Messages stored", len(messages) >= 4))
            checks.append(("Roles alternate correctly", len(user_msgs) == len(asst_msgs)))
            checks.append(
                (
                    "First message is the question",
                    user_msgs[0].content == QUESTION_BASIC if user_msgs else False,
                )
            )
        else:
            print("  SKIP — no conversation to check")

        # ==================================================================
        # STEP 8: Verify action log
        # ==================================================================
        _print_step(8, "Verify action log entries")

        async with async_session_factory() as db:
            result = await db.execute(
                select(ActionLog)
                .where(ActionLog.profile_id == profile_id)
                .order_by(ActionLog.created_at)
            )
            logs = result.scalars().all()

        log_types = [log.action_type for log in logs]
        print(f"  Total log entries: {len(logs)}")
        for log in logs:
            print(f"    [{log.action_type}] {json.dumps(log.payload, default=str)[:80]}")

        checks.append(("chat_message logged", "chat_message" in log_types))

        # ==================================================================
        # STEP 9: Memory extraction — extract and verify
        # ==================================================================
        _print_step(9, "Memory extraction — extract facts from chat and verify")

        if llm_available and turn_a:
            print("  Extracting memories from basic chat turn...")
            await memory_extractor.extract_and_store(
                profile_id=profile_id,
                messages=[
                    {"role": "user", "content": QUESTION_BASIC},
                    {"role": "assistant", "content": turn_a.message.content},
                ],
                source=f"chat:{conversation_id}",
                category="general",
            )
            # Give Mem0 a moment to index
            await asyncio.sleep(2)

            # Search for something we know was discussed
            memories = await memory_service.search(
                profile_id,
                "blood sugar management diabetes tips",
                limit=10,
                threshold=0.05,
            )
            print(f"  Memories found: {len(memories)}")
            for mem in memories[:5]:
                score = mem.get("score", 0)
                text = mem.get("memory", "")
                print(f"    [{score:.2f}] {_truncate(text, 80)}")

            checks.append(("Memories retrievable after extraction", len(memories) > 0))
        else:
            print("  SKIP — no LLM turn to extract from")

        # ==================================================================
        # STEP 10: Mental health crisis detection
        # ==================================================================
        _print_step(10, "Mental health crisis — fast path, no LLM call")
        t0 = time.time()

        async with async_session_factory() as db:
            lp = await db.get(Profile, profile_id)
            svc = ChatService(db, agent_core, context_builder, memory_extractor)
            crisis_convo, crisis_turn = await svc.send_message(lp, CRISIS_MESSAGE)
            await db.commit()

        elapsed = time.time() - t0
        print(f"  Time: {elapsed:.2f}s (should be <1s — no LLM)")
        print(f"  Response: {_truncate(crisis_turn.message.content, 200)}")

        checks.append(("Crisis response fast (<1s)", elapsed < 1.0))
        checks.append(("Crisis response has 988", "988" in crisis_turn.message.content))
        checks.append(
            (
                "Crisis response has Crisis Text Line",
                "Crisis Text Line" in crisis_turn.message.content
                or "741741" in crisis_turn.message.content,
            )
        )
        checks.append(("Crisis disclaimer present", crisis_turn.disclaimer == CHAT_DISCLAIMER))

        # ==================================================================
        # STEP 11: Verify Mem0 has seeded + extracted memories
        # ==================================================================
        _print_step(11, "Verify Mem0 — seed memories + extraction searchable")

        # Query targeting the seed conversations
        seed_memories = await memory_service.search(
            profile_id,
            "HbA1c blood sugar sleep insomnia diabetes",
            limit=10,
            threshold=0.05,
        )
        print(f"  Seed memories found: {len(seed_memories)}")
        for mem in seed_memories[:5]:
            score = mem.get("score", 0)
            text = mem.get("memory", "")
            print(f"    [{score:.2f}] {_truncate(text, 80)}")

        checks.append(("Seed memories searchable", len(seed_memories) > 0))

        # ==================================================================
        # STEP 12: Conversation listing and get
        # ==================================================================
        _print_step(12, "Conversation listing and retrieval")

        async with async_session_factory() as db:
            svc = ChatService(db, agent_core, context_builder, memory_extractor)
            listing = await svc.list_conversations(profile_id)

        print(f"  Total conversations: {listing.total}")
        for convo in listing.items:
            print(f"    [{convo.id}] topic={convo.topic!r}")

        # At minimum: the basic chat conv + profile-aware conv + crisis conv
        checks.append(("At least 3 conversations", listing.total >= 3))

        if listing.items:
            # Verify get_conversation works and returns messages
            async with async_session_factory() as db:
                svc = ChatService(db, agent_core, context_builder, memory_extractor)
                found = await svc.get_conversation(listing.items[0].id, profile_id)

            print(f"  get_conversation: {found is not None}")
            checks.append(("get_conversation works", found is not None))

    finally:
        # ==================================================================
        # CLEANUP
        # ==================================================================
        print(f"\n{'=' * 60}")
        print("  CLEANUP")
        print(f"{'=' * 60}")

        if profile_id:
            try:
                await memory_service.delete_all(profile_id)
                print("  Mem0 memories deleted")
            except Exception as e:
                print(f"  Mem0 cleanup warning: {e}")

            from sqlalchemy import text

            async with async_session_factory() as db:
                await db.execute(
                    text("DELETE FROM action_log WHERE profile_id = :pid"),
                    {"pid": profile_id},
                )
                await db.execute(
                    text("DELETE FROM profiles WHERE id = :pid"),
                    {"pid": profile_id},
                )
                await db.commit()
            print("  DB records deleted")

    # ==================================================================
    # RESULTS
    # ==================================================================
    print(f"\n{'=' * 60}")
    print("  RESULTS")
    print(f"{'=' * 60}")

    passed_count = sum(1 for _, ok in checks if ok)
    failed_count = len(checks) - passed_count

    for name, ok in checks:
        _print_check(name, ok)

    print(f"\n  {passed_count}/{len(checks)} passed", end="")
    if failed_count:
        print(f", {failed_count} FAILED")
    else:
        print()

    all_ok = all(ok for _, ok in checks)
    print(f"\n  {'ALL PASSED' if all_ok else 'FAILED'}")
    return all_ok


if __name__ == "__main__":
    ok = asyncio.run(run())
    sys.exit(0 if ok else 1)
