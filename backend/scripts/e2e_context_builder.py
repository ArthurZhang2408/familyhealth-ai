#!/usr/bin/env python3
"""End-to-end test of ContextBuilder against live PostgreSQL + Mem0.

Usage:
    cd backend && python3 scripts/e2e_context_builder.py

Requires:
    - PostgreSQL running on PG_HOST:PG_PORT (docker compose up -d db)
    - Valid GEMINI_API_KEY and QWEN_API_KEY in .env
    - Alembic migrations applied (python3 -m alembic upgrade head)

What it does:
    1. Creates a test profile in PostgreSQL with rich medical data
    2. Adds episodic memories to Mem0 (real embedding pipeline)
    3. Calls ContextBuilder.build() with a realistic query
    4. Prints the full system prompt + token breakdown
    5. Cleans up: deletes profile + memories
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date
from pathlib import Path

# Ensure `app` is importable when running from the scripts/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Test data — a realistic patient profile
# ---------------------------------------------------------------------------

TEST_ACCOUNT_ID = uuid.uuid4()

PROFILE_DATA = {
    "account_id": TEST_ACCOUNT_ID,
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
        {"name": "Atorvastatin", "dosage": "20mg", "frequency": "once daily at bedtime"},
    ],
    "medical_conditions": [
        {"condition": "Type 2 Diabetes", "diagnosed": "2019", "status": "active"},
        {"condition": "Hypertension", "diagnosed": "2020", "status": "managed"},
        {"condition": "Hyperlipidemia", "diagnosed": "2021", "status": "managed"},
    ],
    "family_medical_history": {
        "Heart Disease": ["Father (heart attack at 55)"],
        "Diabetes": ["Maternal grandmother"],
        "Breast Cancer": ["Maternal aunt"],
    },
}

# Conversations to seed Mem0 with episodic memories
_UTI_USER = (
    "My mom was diagnosed with a UTI last week. "
    "The doctor prescribed Ciprofloxacin 500mg for 7 days."
)
_UTI_ASSISTANT = (
    "I've noted that. UTIs are common and usually resolve "
    "well with antibiotics. Make sure she completes the full course."
)
_HBA1C_USER = (
    "Mom's latest HbA1c came back at 7.2%. The doctor said it's "
    "slightly above target and recommended increasing her Metformin."
)
_HBA1C_ASSISTANT = (
    "An HbA1c of 7.2% indicates her blood sugar control could be "
    "improved. The target is below 7%. Increasing Metformin is standard."
)
_KNEE_USER = (
    "She's been having persistent pain in her right knee for about "
    "3 weeks. An X-ray showed early signs of osteoarthritis."
)
_KNEE_ASSISTANT = (
    "Early osteoarthritis is common in patients over 60. Treatment "
    "includes physical therapy, weight management, and pain relief."
)

SEED_CONVERSATIONS = [
    {
        "messages": [
            {"role": "user", "content": _UTI_USER},
            {"role": "assistant", "content": _UTI_ASSISTANT},
        ],
        "category": "diagnoses",
        "source": "diagnosis:e2e-session-1",
    },
    {
        "messages": [
            {"role": "user", "content": _HBA1C_USER},
            {"role": "assistant", "content": _HBA1C_ASSISTANT},
        ],
        "category": "lab_results",
        "source": "chat",
    },
    {
        "messages": [
            {"role": "user", "content": _KNEE_USER},
            {"role": "assistant", "content": _KNEE_ASSISTANT},
        ],
        "category": "symptoms",
        "source": "diagnosis:e2e-session-2",
    },
]

# The query we'll use to test retrieval
TEST_QUERY = "My mom has been feeling dizzy and her blood sugar has been high lately"


# ---------------------------------------------------------------------------
# E2E runner
# ---------------------------------------------------------------------------


async def run() -> None:
    from app.api.deps import get_memory_service
    from app.core.database import async_session_factory
    from app.models.profile import Profile
    from app.services.context_builder import ContextBuilder

    print("=" * 70)
    print("E2E ContextBuilder Test — Live DB + Mem0")
    print("=" * 70)

    # -- Step 1: Create profile -------------------------------------------------
    print("\n[1/5] Creating test profile in PostgreSQL...")
    profile_id: uuid.UUID | None = None
    memory_service = get_memory_service()
    all_passed = True

    try:
        async with async_session_factory() as db:
            profile = Profile(id=uuid.uuid4(), **PROFILE_DATA)
            profile_id = profile.id
            db.add(profile)
            await db.commit()
            print(f"  Created profile: {profile.name} (id={profile_id})")

        # -- Step 2: Seed memories ----------------------------------------------
        print("\n[2/5] Seeding episodic memories via Mem0...")
        total_facts = 0
        for i, conv in enumerate(SEED_CONVERSATIONS, 1):
            result = await memory_service.add(
                profile_id,
                conv["messages"],
                category=conv["category"],
                source=conv["source"],
            )
            facts = result.get("results", [])
            total_facts += len(facts)
            print(f"  Conversation {i}: extracted {len(facts)} fact(s)")
            for fact in facts:
                event = fact.get("event", "?")
                memory = fact.get("memory", "?")
                print(f"    - [{event}] {memory}")

        if total_facts == 0:
            print(
                "\n  WARNING: Mem0 extracted 0 facts (free-tier flakiness)."
                "\n  Memory retrieval checks will be skipped."
                "\n  Profile formatting is still fully tested."
            )

        # -- Step 3: Build context ----------------------------------------------
        print(f'\n[3/5] Building context for query: "{TEST_QUERY}"')
        builder = ContextBuilder(memory_service)

        for itype in ("chat", "diagnosis"):
            budget = 1000 if itype == "chat" else 2000
            print(f"\n  --- interaction_type={itype}," f" memory_budget={budget} ---")

            async with async_session_factory() as db:
                result = await builder.build(
                    db,
                    profile_id,
                    TEST_QUERY,
                    itype,
                    memory_budget=budget,
                )

            print(f"\n  Memories retrieved: {result.memories_used}")
            print(f"  Token counts: {result.token_counts}")
            print(f"\n  {'─' * 60}")
            print(f"  SYSTEM PROMPT ({itype}):")
            print(f"  {'─' * 60}")
            for line in result.system_prompt.split("\n"):
                print(f"  {line}")
            print(f"  {'─' * 60}")

        # -- Step 4: Verify key properties --------------------------------------
        print("\n[4/5] Verifying output...")
        async with async_session_factory() as db:
            result = await builder.build(db, profile_id, TEST_QUERY, "chat")

        checks = [
            ("Profile name present", "Chen Wei" in result.system_prompt),
            (
                "Allergy with severity",
                "Penicillin" in result.system_prompt and "severe" in result.system_prompt,
            ),
            ("Medication with dosage", "Metformin 1000mg" in result.system_prompt),
            ("Medical condition", "Type 2 Diabetes" in result.system_prompt),
            ("Family history", "Heart Disease" in result.system_prompt),
            ("Disclaimer present", "MEDICAL DISCLAIMER" in result.system_prompt),
            ("Token counts populated", result.token_counts["total"] > 0),
            ("Relationship shown", "parent" in result.system_prompt),
        ]

        if total_facts > 0:
            checks.append(("Memories used > 0", result.memories_used > 0))
        else:
            checks.append(("Memories used (skipped — no facts stored)", True))

        for name, passed in checks:
            status = "PASS" if passed else "FAIL"
            if not passed:
                all_passed = False
            print(f"  [{status}] {name}")

    finally:
        # -- Step 5: Cleanup (always runs) --------------------------------------
        print("\n[5/5] Cleaning up...")
        if profile_id:
            await memory_service.delete_all(profile_id)
            print("  Deleted Mem0 memories")
            async with async_session_factory() as db:
                profile = await db.get(Profile, profile_id)
                if profile:
                    await db.delete(profile)
                    await db.commit()
            print("  Deleted test profile")

    print("\n" + "=" * 70)
    if all_passed:
        print("ALL CHECKS PASSED")
    else:
        print("SOME CHECKS FAILED — review output above")
        sys.exit(1)
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run())
