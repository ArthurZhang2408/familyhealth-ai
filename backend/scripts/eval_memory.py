#!/usr/bin/env python3
"""Memory & agent evaluation script — inspect what the agent saw, did, and why.

Usage:
    python scripts/eval_memory.py latest                     # latest session overview
    python scripts/eval_memory.py session <session_id>       # specific session overview
    python scripts/eval_memory.py debug                      # latest session agent debug
    python scripts/eval_memory.py debug <session_id>         # specific session agent debug
    python scripts/eval_memory.py memories <profile_id>      # all stored memories
    python scripts/eval_memory.py quality <profile_id>       # quality report (flag issues)
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Quality heuristics
# ---------------------------------------------------------------------------

INSTRUCTION_PATTERNS = [
    re.compile(r"^seek immediate", re.IGNORECASE),
    re.compile(r"^avoid\b", re.IGNORECASE),
    re.compile(r"^do not\b", re.IGNORECASE),
    re.compile(r"^take \w+ \d+mg", re.IGNORECASE),
    re.compile(r"^check back in", re.IGNORECASE),
    re.compile(r"^stay hydrated", re.IGNORECASE),
    re.compile(r"recommended as OTC", re.IGNORECASE),
]

NEGATION_PATTERNS = [
    re.compile(r"\bdenies\b", re.IGNORECASE),
    re.compile(r"\bno\b.*\bsymptoms?\b", re.IGNORECASE),
    re.compile(r"\bnot present\b", re.IGNORECASE),
    re.compile(r"\bnone\b.*\breported\b", re.IGNORECASE),
]


def flag_memory(text: str) -> list[str]:
    """Return a list of warning flags for a memory text."""
    flags = []
    for pat in INSTRUCTION_PATTERNS:
        if pat.search(text):
            flags.append("LOOKS_LIKE_INSTRUCTION")
            break
    for pat in NEGATION_PATTERNS:
        if pat.search(text):
            flags.append("CONTAINS_NEGATION")
            break
    return flags


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def print_header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_section(title: str) -> None:
    print(f"\n--- {title} ---")


def format_score_bar(score: float, width: int = 20) -> str:
    filled = int(score * width)
    return f"[{'#' * filled}{'.' * (width - filled)}] {score:.3f}"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


async def get_engine():
    from app.core.config import Settings
    from sqlalchemy.ext.asyncio import create_async_engine

    settings = Settings()
    return create_async_engine(settings.database_url)


async def get_latest_session(engine):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine) as db:
        result = await db.execute(
            text(
                "SELECT id, profile_id, chief_complaint, status, created_at "
                "FROM diagnosis_sessions ORDER BY created_at DESC LIMIT 1"
            )
        )
        row = result.first()
        if not row:
            print("No diagnosis sessions found.")
            sys.exit(1)
        return dict(row._mapping)


async def get_session_by_id(engine, session_id: UUID):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine) as db:
        result = await db.execute(
            text(
                "SELECT id, profile_id, chief_complaint, status, created_at "
                "FROM diagnosis_sessions WHERE id = :sid"
            ),
            {"sid": session_id},
        )
        row = result.first()
        if not row:
            print(f"Session {session_id} not found.")
            sys.exit(1)
        return dict(row._mapping)


async def get_traces(engine, session_id: UUID):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine) as db:
        result = await db.execute(
            text(
                "SELECT event_type, turn_number, payload, created_at "
                "FROM memory_traces WHERE session_id = :sid "
                "ORDER BY created_at ASC"
            ),
            {"sid": session_id},
        )
        return [dict(r._mapping) for r in result.all()]


async def get_messages(engine, session_id: UUID):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine) as db:
        result = await db.execute(
            text(
                "SELECT role, content, content_parts, metadata, created_at "
                "FROM diagnosis_messages WHERE session_id = :sid "
                "ORDER BY created_at ASC"
            ),
            {"sid": session_id},
        )
        return [dict(r._mapping) for r in result.all()]


async def get_all_memories(engine, profile_id: UUID):
    """Fetch all memories from Mem0's pgvector store."""
    import subprocess

    # Use docker exec since Mem0 uses a separate database
    result = subprocess.run(
        [
            "docker",
            "exec",
            "familyhealth-ai-db-1",
            "psql",
            "-U",
            "familyhealth",
            "-d",
            "mem0_db",
            "-t",
            "-A",
            "-F",
            "\t",
            "-c",
            f"SELECT id, payload->>'data' as memory, "
            f"payload->'metadata'->>'category' as category, "
            f"payload->'metadata'->>'source' as source "
            f"FROM health_memories "
            f"WHERE payload->>'user_id' = '{profile_id}' "
            f"ORDER BY id",
        ],
        capture_output=True,
        text=True,
    )
    memories = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            memories.append(
                {
                    "id": parts[0],
                    "memory": parts[1],
                    "category": parts[2] if len(parts) > 2 else "",
                    "source": parts[3] if len(parts) > 3 else "",
                }
            )
    return memories


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


async def cmd_session(engine, session_id: UUID | None = None):
    """Show full memory trace for a session."""
    if session_id:
        session = await get_session_by_id(engine, session_id)
    else:
        session = await get_latest_session(engine)

    sid = session["id"]
    print_header(f"Session: {session['chief_complaint']}")
    print(f"  ID:     {sid}")
    print(f"  Status: {session['status']}")
    print(f"  Date:   {session['created_at']}")

    # Get traces
    traces = await get_traces(engine, sid)
    messages = await get_messages(engine, sid)

    if not traces:
        print("\n  No memory traces recorded for this session.")
        print("  (Traces are only recorded after the eval framework was added.)")
    else:
        # Retrieval traces
        retrievals = [t for t in traces if t["event_type"] == "retrieval"]
        for i, t in enumerate(retrievals):
            payload = t["payload"]
            print_section(f"Retrieval (turn {t.get('turn_number') or i + 1})")
            print(f"  Query: \"{payload.get('query', '')}\"")
            print(
                f"  Retrieved: {payload.get('retrieved_count', 0)} | "
                f"Injected: {payload.get('injected_count', 0)}"
            )
            results = payload.get("results", [])
            if results:
                print()
                for j, r in enumerate(results):
                    score = r.get("score", 0)
                    mem_text = r.get("memory", "")
                    flags = flag_memory(mem_text)
                    flag_str = f"  {'  '.join(flags)}" if flags else ""
                    print(f"  {j + 1:>3}. {format_score_bar(score)}  {mem_text[:80]}{flag_str}")

        # Extraction traces
        extractions = [t for t in traces if t["event_type"] == "extraction"]
        for t in extractions:
            payload = t["payload"]
            print_section("Extraction (post-session)")
            print(f"  Input messages: {payload.get('input_message_count', 0)}")
            print(f"  Facts stored: {payload.get('facts_stored', 0)}")
            results = payload.get("results", [])
            for r in results:
                event = r.get("event", "?")
                mem_text = r.get("memory", "")
                flags = flag_memory(mem_text)
                flag_str = f"  {'  '.join(flags)}" if flags else ""
                print(f"    [{event:>6}] {mem_text}{flag_str}")

    # Show conversation summary
    print_section("Conversation")
    for msg in messages:
        role = msg["role"]
        content = (msg["content"] or "")[:120]
        parts = msg.get("content_parts") or []
        part_types = [p.get("type", "?") for p in parts if isinstance(p, dict)]
        parts_str = f"  parts: {', '.join(part_types)}" if part_types else ""
        print(f"  [{role:>9}] {content or '(empty)'}{parts_str}")


async def cmd_debug(engine, session_id: UUID | None = None):
    """Show detailed agent debug info: what the agent saw and did at each turn."""
    if session_id:
        session = await get_session_by_id(engine, session_id)
    else:
        session = await get_latest_session(engine)

    sid = session["id"]
    print_header(f"Agent Debug: {session['chief_complaint']}")
    print(f"  ID: {sid}")

    messages = await get_messages(engine, sid)
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]

    for i, msg in enumerate(assistant_msgs):
        meta = msg.get("metadata") or {}
        if not meta:
            print(f"\n--- Turn {i + 1}: No debug metadata ---")
            continue

        turn = meta.get("turn_number", "?")
        print(f"\n{'=' * 50}")
        print(f"  TURN {turn} (assistant message {i + 1})")
        print(f"{'=' * 50}")

        # Show enriched conversation history the agent saw
        history = meta.get("enriched_history", [])
        if history:
            print(f"\n  Conversation history sent to LLM ({len(history)} messages):")
            for j, m in enumerate(history):
                role = m.get("role", "?")
                content = m.get("content", "")
                thinking = " [+thinking]" if m.get("has_thinking") else ""
                if not content.strip() or content == "(thinking only)":
                    print(f"    {j + 1}. [{role:>9}] *** EMPTY ***{thinking}")
                else:
                    print(f"    {j + 1}. [{role:>9}] {content[:150]}{thinking}")

        # Show agent rounds
        rounds = meta.get("agent_rounds", [])
        if rounds:
            print(f"\n  Agent loop ({len(rounds)} rounds):")
            for r in rounds:
                tc_str = ", ".join(tc["name"] for tc in r.get("tool_calls", []))
                text_len = r.get("text_length", 0)
                preview = r.get("text_preview", "")[:100]
                status = []
                if tc_str:
                    status.append(f"tools: [{tc_str}]")
                if text_len:
                    status.append(f"text: {text_len} chars")
                elif not tc_str:
                    status.append("*** NO OUTPUT ***")
                print(f"    Round {r.get('round', '?')}: {' | '.join(status)}")
                if preview:
                    print(f'      "{preview}"')

        # Show what the agent actually produced
        content = msg.get("content") or ""
        parts = msg.get("content_parts") or []
        questions = [
            p for p in parts if isinstance(p, dict) and p.get("type") == "structured_input"
        ]
        thinking = [p for p in parts if isinstance(p, dict) and p.get("type") == "thinking"]

        print(f"\n  Output:")
        print(f"    Text: {content[:150] if content else '(empty)'}")
        if questions:
            for q in questions:
                opts = [
                    o.get("label", "") for o in (q.get("options") or []) if isinstance(o, dict)
                ]
                print(f"    Question: \"{q.get('prompt', '')}\" [{q.get('input_type', '')}]")
                if opts:
                    print(f"      Options: {', '.join(opts)}")
        if thinking:
            t = thinking[0].get("text", "")
            print(f"    Thinking: {len(t)} chars")
            # Show last paragraph (usually the decision)
            paragraphs = [p.strip() for p in t.split("\n\n") if p.strip()]
            if paragraphs:
                print(f'    Last thought: "{paragraphs[-1][:200]}"')

        print(f"    Memories used: {meta.get('memories_used', '?')}")


async def cmd_memories(engine, profile_id: UUID):
    """List all stored memories for a profile."""
    memories = await get_all_memories(engine, profile_id)
    print_header(f"Stored Memories for {profile_id}")
    print(f"  Total: {len(memories)}")

    for i, m in enumerate(memories):
        flags = flag_memory(m["memory"])
        flag_str = f"  {'  '.join(flags)}" if flags else ""
        category = m.get("category") or "?"
        print(f"  {i + 1:>3}. [{category:>15}] {m['memory']}{flag_str}")

    # Summary
    flagged = [m for m in memories if flag_memory(m["memory"])]
    if flagged:
        print_section(f"Flagged Memories ({len(flagged)})")
        for m in flagged:
            flags = flag_memory(m["memory"])
            print(f"    {' | '.join(flags):>25}  {m['memory'][:80]}")


async def cmd_quality(engine, profile_id: UUID):
    """Quality report — flag issues across stored memories."""
    memories = await get_all_memories(engine, profile_id)
    print_header(f"Memory Quality Report for {profile_id}")
    print(f"  Total memories: {len(memories)}")

    # Check for instructions
    instructions = [
        m for m in memories if any(p.search(m["memory"]) for p in INSTRUCTION_PATTERNS)
    ]
    if instructions:
        print_section(f"Memories that look like INSTRUCTIONS ({len(instructions)})")
        for m in instructions:
            print(f"    - {m['memory']}")
    else:
        print("\n  No instruction-like memories found.")

    # Check for negations
    negations = [m for m in memories if any(p.search(m["memory"]) for p in NEGATION_PATTERNS)]
    if negations:
        print_section(f"Memories with NEGATIONS (risk of misread) ({len(negations)})")
        for m in negations:
            print(f"    - {m['memory']}")

    # Check for duplicates
    seen_texts: dict[str, list] = {}
    for m in memories:
        text = m["memory"].lower().strip()
        seen_texts.setdefault(text, []).append(m)
    dupes = {t: ms for t, ms in seen_texts.items() if len(ms) > 1}
    if dupes:
        print_section(f"DUPLICATE memories ({len(dupes)} groups)")
        for text, ms in dupes.items():
            print(f"    x{len(ms)}: {ms[0]['memory'][:80]}")

    # Summary
    total_issues = len(instructions) + len(negations) + sum(len(ms) - 1 for ms in dupes.values())
    print(f"\n  Total issues: {total_issues}")
    if total_issues == 0:
        print("  Memory quality looks good!")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    engine = await get_engine()

    try:
        if cmd == "latest":
            await cmd_session(engine)
        elif cmd == "session" and len(sys.argv) >= 3:
            await cmd_session(engine, UUID(sys.argv[2]))
        elif cmd == "memories" and len(sys.argv) >= 3:
            await cmd_memories(engine, UUID(sys.argv[2]))
        elif cmd == "quality" and len(sys.argv) >= 3:
            await cmd_quality(engine, UUID(sys.argv[2]))
        elif cmd == "debug":
            sid = UUID(sys.argv[2]) if len(sys.argv) >= 3 else None
            await cmd_debug(engine, sid)
        else:
            print(__doc__)
            sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
