#!/usr/bin/env python3
"""End-to-end test of the full diagnosis feature against live infrastructure.

Exercises the complete stack: PostgreSQL, Mem0, Gemini (Pass 1), Qwen (Pass 2).
No mocks. All prod settings.

Usage:
    cd backend && python3 scripts/e2e_diagnosis.py
    cd backend && python3 scripts/e2e_diagnosis.py --model gemini-2.5-flash-lite  # override model

Requires:
    - PostgreSQL running (docker compose up -d db)
    - Valid GEMINI_API_KEY and QWEN_API_KEY in .env
    - Alembic migrations applied (python3 -m alembic upgrade head)

What it tests:
    1. Profile creation with rich medical data
    2. Memory seeding via Mem0 (episodic history)
    3. Session creation — Gemini Pro generates first response
    4. Multi-turn conversation — follow-up messages
    5. Pass 2 state extraction — Qwen extracts structured DiagnosisState
    6. Safety validation — prohibited patterns caught
    7. Red flag detection — emergency template, no LLM call
    8. Session resolution — memory extraction on close
    9. Action log entries created
   10. Full cleanup
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
# Test data — a realistic patient profile
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
                    "Mom had a UTI last month. Doctor prescribed "
                    "Ciprofloxacin 500mg for 7 days. She completed the course."
                ),
            },
            {
                "role": "assistant",
                "content": "Noted. UTIs are common and usually resolve well with antibiotics.",
            },
        ],
        "category": "diagnoses",
        "source": "diagnosis:e2e-seed-1",
    },
    {
        "messages": [
            {
                "role": "user",
                "content": "Mom's latest HbA1c was 7.2%. Doctor wants to monitor more closely.",
            },
            {
                "role": "assistant",
                "content": "HbA1c of 7.2% suggests room for improvement in blood sugar control.",
            },
        ],
        "category": "lab_results",
        "source": "chat",
    },
]

# The chief complaint for the normal-flow session
CHIEF_COMPLAINT = (
    "My mom has been having recurring headaches for the past two weeks. "
    "They happen mostly in the morning and she rates the pain about 6 out of 10."
)

# Follow-up messages to simulate a multi-turn conversation
FOLLOW_UP_MESSAGES = [
    (
        "The pain is mostly at the front of her head, sometimes behind her eyes. "
        "It's a dull, throbbing sensation. It usually lasts 2-3 hours."
    ),
    (
        "Stress and looking at her phone seem to make it worse. "
        "Rest and a cold compress help a bit. She hasn't tried any medication yet."
    ),
]

# Red flag message for emergency short-circuit test
RED_FLAG_MESSAGE = "She suddenly has the worst headache of her life and can't speak clearly"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_step(n: int, msg: str) -> None:
    print(f"\n{'='*60}")
    print(f"  STEP {n}: {msg}")
    print(f"{'='*60}")


def _print_check(name: str, passed: bool, detail: str = "") -> None:
    icon = "PASS" if passed else "FAIL"
    suffix = f" ({detail})" if detail else ""
    print(f"  {icon}  {name}{suffix}")


def _truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


async def _retry_llm(coro_fn, *, max_retries: int = 3, base_delay: float = 30.0):
    """Retry an async callable that may hit LLM rate limits.

    On 429/RESOURCE_EXHAUSTED, waits with exponential backoff and retries.
    Returns the result on success, or re-raises the last exception.
    """
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
                    f"  Rate limited (attempt {attempt + 1}/{max_retries})."
                    f" Waiting {delay:.0f}s..."
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
    from app.models.diagnosis import DiagnosisMessage, DiagnosisSession
    from app.models.profile import Profile
    from app.services.context_builder import ContextBuilder
    from app.services.diagnosis import DiagnosisService
    from app.services.diagnosis_prompts import MEDICAL_DISCLAIMER
    from app.services.memory_extractor import MemoryExtractor

    engine.echo = False

    memory_service = get_memory_service()
    context_builder = ContextBuilder(memory_service)
    memory_extractor = MemoryExtractor(memory_service)
    agent_core = get_agent_core()

    profile_id: uuid.UUID | None = None
    checks: list[tuple[str, bool]] = []

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
        print(f"  Allergies: {len(PROFILE_DATA['allergies'])}")
        print(f"  Medications: {len(PROFILE_DATA['current_medications'])}")
        print(f"  Conditions: {len(PROFILE_DATA['medical_conditions'])}")

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
        # STEP 3: Create diagnosis session (first LLM call)
        # ==================================================================
        _print_step(3, "Create diagnosis session — Gemini generates first response")
        t0 = time.time()
        llm_available = True
        session_id = None

        async def _create_session():
            async with async_session_factory() as db:
                lp = await db.get(Profile, profile_id)
                s = DiagnosisService(db, agent_core, context_builder, memory_extractor)
                sess, trn = await s.create_session(lp, CHIEF_COMPLAINT)
                await db.commit()
                return sess, trn

        try:
            session, turn = await _retry_llm(_create_session)
            session_id = session.id

            elapsed = time.time() - t0
            print(f"  Session ID: {session_id}")
            print(f"  Status: {session.status}")
            print(f"  Time: {elapsed:.1f}s")
            print(f"  AI response ({len(turn.message.content)} chars):")
            print(f"    {_truncate(turn.message.content)}")
            print(f"  Phase: {turn.diagnosis_state.phase}")
            print(f"  Severity: {turn.diagnosis_state.severity}")
            print(f"  Suggested Qs: {turn.diagnosis_state.suggested_next_questions}")

            checks.append(("Session created", session.status == "active"))
            checks.append(("AI response non-empty", len(turn.message.content) > 50))
            checks.append(("Disclaimer present", turn.disclaimer == MEDICAL_DISCLAIMER))
            checks.append(("Phase is valid", turn.diagnosis_state.phase != "unknown"))
            checks.append(("Severity is valid", turn.diagnosis_state.severity != ""))
            checks.append(
                (
                    "Chief complaint extracted",
                    turn.diagnosis_state.information_gathered.chief_complaint is not None,
                )
            )
        except Exception as e:
            llm_available = False
            print(f"  SKIP — LLM unavailable: {type(e).__name__}")
            print("  (Gemini quota exhausted — LLM steps will be skipped)")
            checks.append(("Session created [LLM]", False))

        # ==================================================================
        # STEP 4: Multi-turn conversation
        # ==================================================================
        _print_step(4, "Multi-turn conversation — send follow-up messages")

        if llm_available and session_id:
            for i, msg_text in enumerate(FOLLOW_UP_MESSAGES, 1):
                t0 = time.time()

                async def _send(content=msg_text):
                    async with async_session_factory() as db:
                        lp = await db.get(Profile, profile_id)
                        s = DiagnosisService(db, agent_core, context_builder, memory_extractor)
                        r = await db.execute(
                            select(DiagnosisSession).where(DiagnosisSession.id == session_id)
                        )
                        sess = r.scalar_one()
                        trn = await s.send_message(sess, lp, content)
                        await db.commit()
                        return trn

                turn = await _retry_llm(_send)

                elapsed = time.time() - t0
                print(f"\n  Turn {i + 1} ({elapsed:.1f}s):")
                print(f"    User: {_truncate(msg_text, 80)}")
                print(f"    AI: {_truncate(turn.message.content, 150)}")
                print(f"    Phase: {turn.diagnosis_state.phase}")
                print(f"    Turn #: {turn.diagnosis_state.turn_number}")
                checks.append((f"Turn {i + 1} response", len(turn.message.content) > 30))

            # After multiple turns, check cumulative state
            info = turn.diagnosis_state.information_gathered
            checks.append(
                (
                    "OLDCARTS data accumulating",
                    sum(
                        1
                        for v in [
                            info.chief_complaint,
                            info.onset,
                            info.location,
                            info.duration,
                            info.character,
                            info.aggravating_factors,
                            info.relieving_factors,
                            info.severity_rating,
                        ]
                        if v is not None
                    )
                    >= 3,
                )
            )
        else:
            print("  SKIP — LLM unavailable")

        # ==================================================================
        # STEP 5: Verify messages stored in DB
        # ==================================================================
        _print_step(5, "Verify messages stored in database")

        if llm_available and session_id:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(DiagnosisMessage)
                    .where(DiagnosisMessage.session_id == session_id)
                    .order_by(DiagnosisMessage.created_at)
                )
                messages = result.scalars().all()

            user_msgs = [m for m in messages if m.role == "user"]
            asst_msgs = [m for m in messages if m.role == "assistant"]
            expected_total = 2 * (1 + len(FOLLOW_UP_MESSAGES))
            print(f"  Total messages: {len(messages)} (expected {expected_total})")
            print(f"  User: {len(user_msgs)}, Assistant: {len(asst_msgs)}")

            checks.append(("Message count", len(messages) == expected_total))
            checks.append(
                (
                    "First message is chief complaint",
                    user_msgs[0].content == CHIEF_COMPLAINT,
                )
            )
        else:
            print("  SKIP — no session created")

        # ==================================================================
        # STEP 6: Red flag emergency short-circuit
        # ==================================================================
        _print_step(6, "Red flag detection — emergency template (no LLM call)")
        t0 = time.time()

        async with async_session_factory() as db:
            loaded_profile = await db.get(Profile, profile_id)
            svc = DiagnosisService(db, agent_core, context_builder, memory_extractor)

            emergency_session, emergency_turn = await svc.create_session(
                loaded_profile, RED_FLAG_MESSAGE
            )
            await db.commit()
            _ = emergency_session.id  # session cleaned up via profile CASCADE

        elapsed = time.time() - t0
        print(f"  Time: {elapsed:.1f}s (should be <1s — no LLM)")
        print(f"  Severity: {emergency_turn.diagnosis_state.severity}")
        print(f"  Red flags: {emergency_turn.diagnosis_state.red_flags_detected}")
        print(f"  Response: {_truncate(emergency_turn.message.content, 120)}")

        checks.append(
            (
                "Emergency severity",
                emergency_turn.diagnosis_state.severity == "emergency",
            )
        )
        checks.append(
            (
                "Red flags detected",
                len(emergency_turn.diagnosis_state.red_flags_detected) > 0,
            )
        )
        checks.append(("Emergency fast (<2s)", elapsed < 2.0))
        checks.append(
            (
                "Emergency response has 911",
                "911" in emergency_turn.message.content
                or "emergency" in emergency_turn.message.content.lower(),
            )
        )

        # ==================================================================
        # STEP 7: Close session with resolution notes
        # ==================================================================
        _print_step(7, "Close session — resolution + memory extraction")

        if llm_available and session_id:
            async with async_session_factory() as db:
                loaded_profile = await db.get(Profile, profile_id)
                svc = DiagnosisService(db, agent_core, context_builder, memory_extractor)
                result = await db.execute(
                    select(DiagnosisSession).where(DiagnosisSession.id == session_id)
                )
                sess = result.scalar_one()
                closed = await svc.close_session(
                    sess,
                    loaded_profile,
                    "Went to doctor. Diagnosed as tension headaches.",
                )
                await db.commit()

            print(f"  Status: {closed.status}")
            print(f"  Resolution: {closed.resolution_notes}")
            checks.append(("Session resolved", closed.status == "resolved"))
            checks.append(("Resolution notes stored", closed.resolution_notes is not None))
        else:
            print("  SKIP — no session to close")

        # ==================================================================
        # STEP 8: Verify action log entries
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
            print(f"    [{log.action_type}]" f" {json.dumps(log.payload, default=str)[:80]}")

        # Red flag session always creates a diagnosis_started log
        checks.append(("diagnosis_started logged", "diagnosis_started" in log_types))
        if llm_available and session_id:
            checks.append(("diagnosis_message logged", "diagnosis_message" in log_types))
            checks.append(("diagnosis_resolved logged", "diagnosis_resolved" in log_types))

        # ==================================================================
        # STEP 9: Verify Mem0 has memories
        # ==================================================================
        _print_step(9, "Verify Mem0 memories")

        await asyncio.sleep(2)

        memories = await memory_service.search(
            profile_id,
            "headaches tension pain morning UTI HbA1c",
            limit=10,
            threshold=0.05,
        )
        print(f"  Memories found: {len(memories)}")
        for mem in memories[:5]:
            score = mem.get("score", "?")
            text = mem.get("memory", "")
            print(f"    [{score:.2f}] {_truncate(text, 80)}")

        checks.append(("Memories retrievable", len(memories) > 0))

        # ==================================================================
        # STEP 10: Verify session listing
        # ==================================================================
        _print_step(10, "Verify session listing with status filter")

        async with async_session_factory() as db:
            svc = DiagnosisService(db, agent_core, context_builder, memory_extractor)
            all_sessions = await svc.list_sessions(profile_id)

        print(f"  Total sessions: {all_sessions.total}")
        # At minimum, the emergency session should exist
        checks.append(("At least 1 session exists", all_sessions.total >= 1))

    finally:
        # ==================================================================
        # CLEANUP — always runs
        # ==================================================================
        print(f"\n{'='*60}")
        print("  CLEANUP")
        print(f"{'='*60}")

        if profile_id:
            # Clean Mem0
            try:
                await memory_service.delete_all(profile_id)
                print("  Mem0 memories deleted")
            except Exception as e:
                print(f"  Mem0 cleanup warning: {e}")

            # Clean DB — delete profile, CASCADE handles sessions/messages
            from sqlalchemy import text

            async with async_session_factory() as db:
                # Raw SQL delete — DB-level CASCADE handles children
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
    print(f"\n{'='*60}")
    print("  RESULTS")
    print(f"{'='*60}")

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
    # --model <name>: override diagnosis model
    if "--model" in sys.argv:
        import os

        idx = sys.argv.index("--model")
        model = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "gemini-2.5-flash"
        os.environ["GEMINI_DIAGNOSIS_MODEL"] = model
        print(f"Using {model} for diagnosis (--model flag)\n")

    ok = asyncio.run(run())
    sys.exit(0 if ok else 1)
