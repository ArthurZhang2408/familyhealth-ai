#!/usr/bin/env python3
"""End-to-end test of ContextBuilder against live PostgreSQL + Mem0.

Usage:
    cd backend && python3 scripts/e2e_context_builder.py

Requires:
    - PostgreSQL running (docker compose up -d db)
    - Valid GEMINI_API_KEY and QWEN_API_KEY in .env
    - Alembic migrations applied (python3 -m alembic upgrade head)
"""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Silence SQLAlchemy SQL echo and Mem0 internals during the test
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

SEED_CONVERSATIONS = [
    {
        "messages": [
            {
                "role": "user",
                "content": (
                    "My mom was diagnosed with a UTI last week. "
                    "The doctor prescribed Ciprofloxacin 500mg for 7 days."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "I've noted that. UTIs are common and usually resolve "
                    "well with antibiotics. Complete the full course."
                ),
            },
        ],
        "category": "diagnoses",
        "source": "diagnosis:e2e-1",
    },
    {
        "messages": [
            {
                "role": "user",
                "content": (
                    "Mom's latest HbA1c came back at 7.2%. The doctor "
                    "recommended increasing her Metformin."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "An HbA1c of 7.2% means blood sugar control needs "
                    "improvement. Increasing Metformin is standard."
                ),
            },
        ],
        "category": "lab_results",
        "source": "chat",
    },
    {
        "messages": [
            {
                "role": "user",
                "content": (
                    "She has persistent right knee pain for 3 weeks. "
                    "X-ray showed early osteoarthritis."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Early osteoarthritis is common over 60. Treatment "
                    "includes physical therapy and weight management."
                ),
            },
        ],
        "category": "symptoms",
        "source": "diagnosis:e2e-2",
    },
]

TEST_QUERY = "My mom has been feeling dizzy and her blood sugar " "has been high lately"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run() -> bool:
    from app.api.deps import get_memory_service
    from app.core.database import async_session_factory, engine
    from app.models.profile import Profile
    from app.services.context_builder import ContextBuilder

    # Disable SQL echo for clean output
    engine.echo = False

    memory_service = get_memory_service()
    profile_id: uuid.UUID | None = None
    passed: list[tuple[str, bool]] = []

    try:
        # 1. Create profile
        print("[1] Creating profile...", end=" ")
        async with async_session_factory() as db:
            profile = Profile(id=uuid.uuid4(), **PROFILE_DATA)
            profile_id = profile.id
            db.add(profile)
            await db.commit()
        print(f"OK ({profile_id})")

        # 2. Seed memories
        print("[2] Seeding memories via Mem0...")
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
            for f in facts:
                print(f"    [{f.get('event')}] {f.get('memory')}")
        print(f"    Total: {total_facts} facts extracted")

        # 3. Build context for both interaction types
        print("[3] Building context...")
        builder = ContextBuilder(memory_service)

        for itype, budget in [("chat", 1000), ("diagnosis", 2000)]:
            async with async_session_factory() as db:
                ctx = await builder.build(
                    db,
                    profile_id,
                    TEST_QUERY,
                    itype,
                    memory_budget=budget,
                )
            print(
                f"\n    [{itype}] {ctx.memories_used} memories, "
                f"{ctx.token_counts['total']} tokens"
            )
            print("    " + "─" * 56)
            for line in ctx.system_prompt.split("\n"):
                print(f"    {line}")
            print("    " + "─" * 56)

        # 4. Verify
        print("\n[4] Verifying...")
        async with async_session_factory() as db:
            ctx = await builder.build(db, profile_id, TEST_QUERY, "chat")

        p = ctx.system_prompt
        passed = [
            ("Profile name", "Chen Wei" in p),
            ("Allergy severity", "Penicillin" in p and "severe" in p),
            ("Medication dosage", "Metformin 1000mg" in p),
            ("Condition status", "Type 2 Diabetes" in p and "active" in p),
            ("Family history", "Heart Disease" in p),
            ("Relationship", "parent" in p),
            ("Disclaimer", "MEDICAL DISCLAIMER" in p),
            ("Token count", ctx.token_counts["total"] > 0),
        ]
        if total_facts > 0:
            passed.append(("Memories retrieved", ctx.memories_used > 0))

        for name, ok in passed:
            print(f"    {'PASS' if ok else 'FAIL'} {name}")

    finally:
        # 5. Cleanup — always runs
        print("\n[5] Cleanup...", end=" ")
        if profile_id:
            try:
                await memory_service.delete_all(profile_id)
            except Exception:
                pass
            async with async_session_factory() as db:
                p = await db.get(Profile, profile_id)
                if p:
                    await db.delete(p)
                    await db.commit()
        print("OK")

    all_ok = all(ok for _, ok in passed)
    print(f"\n{'ALL PASSED' if all_ok else 'FAILED'}")
    return all_ok


if __name__ == "__main__":
    ok = asyncio.run(run())
    sys.exit(0 if ok else 1)
