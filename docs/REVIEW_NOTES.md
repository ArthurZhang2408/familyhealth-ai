# Documentation Review Notes

## Resolution Status

All items below have been reviewed and resolved. See git history for the changes applied.

---

Review of `ARCHITECTURE.md`, `API_SPEC.md`, `MEMORY_SYSTEM.md`, `DIAGNOSIS_AGENT.md`, and `CLAUDE.md`.

---

## 1. Inconsistencies Between Documents

### 1.1 ~~Mem0 LLM provider conflict~~ ✅ RESOLVED

Both docs now use `nemotron-3-nano:30b` via Ollama Cloud. Diagnosis extraction bypasses Mem0's internal LLM entirely (Cerebras `FACT_EXTRACTION` + `add_raw(infer=False)`).

### 1.2 ~~MemoryService sync vs async~~ ✅ RESOLVED

Both docs show `async def` with `asyncio.to_thread()` wrapping Mem0's sync calls.

### 1.3 ~~MemoryService.search() return type~~ ✅ RESOLVED

Both docs use the unwrapped `result.get("results", [])` pattern.

### 1.4 ~~Diagnosis structured output tag~~ ✅ RESOLVED

Inline tag parsing eliminated. State extraction now uses a separate post-DONE `_extract_state()` call with `FACT_EXTRACTION` task (JSON mode). No `<diagnosis_state>` or `<differential>` tags in prompts.

### 1.5 ~~DifferentialDiagnosis schema~~ ✅ RESOLVED

All docs now use 5-field schema: `{ condition, confidence, reasoning, action_plan, urgency }`.

### 1.6 Chat `per_page` default (LOW)

- API_SPEC.md conventions section: default `per_page` = 20.
- API_SPEC.md `GET /profiles/{pid}/chat`: default `per_page` = 50.

Intentional or oversight? If intentional, document the exception.

### 1.7 ~~`LLMService` vs `LLMProvider` naming~~ ✅ RESOLVED

CLAUDE.md now uses `LLMProvider` + `LLMRouter`.

### 1.8 Security table formatting (LOW)

ARCHITECTURE.md Section 6 "Security Summary" table has `|-|-|-|` (3 columns) but the table only has 2 data columns. Renders incorrectly in some Markdown parsers.

---

## 2. Missing Details That Block Implementation

### 2.1 ~~OpenAI embedding dependency undocumented~~ ✅ RESOLVED

Using Gemini embeddings (`models/gemini-embedding-001`, 768 dims). No OpenAI dependency. Reuses existing Gemini API key.

### 2.2 ~~Qwen API provider unspecified~~ ✅ RESOLVED

Qwen `qwen3.5:397b` via Ollama Cloud (OpenAI-compatible API). Cerebras `gpt-oss-120b` is now the primary provider. Qwen is fallback only.

### 2.3 Background task mechanism (HIGH)

MEMORY_SYSTEM.md says extraction is a "post-interaction background task" that "never blocks the request." No mechanism is specified. Options for FastAPI:
- `BackgroundTasks` (simple, in-process, lost on crash)
- `asyncio.create_task()` (same trade-offs)
- Celery / arq / dramatiq (reliable, needs Redis/RabbitMQ)

For a health app where losing extracted memories is tolerable (they'll be re-extracted), `BackgroundTasks` is fine for v1 — but this should be an explicit decision.

### 2.4 ~~Neo4j deployment~~ ✅ RESOLVED

Neo4j / graph memory deferred to v2. Not in the current stack. pgvector only.

### 2.5 Push notification infrastructure (MEDIUM)

DIAGNOSIS_AGENT.md describes check-in notifications ("push notification") but no notification system is specified. React Native options:
- Expo Push Notifications (simplest with Expo)
- Firebase Cloud Messaging

Also: no cron/scheduler infrastructure for the "background cron job that scans for stale sessions."

### 2.6 Database migration tooling (MEDIUM)

No mention of Alembic or any migration strategy. The DDL is provided as raw SQL. Any schema change will need a migration plan.

### 2.7 Report presigned URL trigger (MEDIUM)

API_SPEC.md Flow B says after uploading to the presigned URL, analysis is triggered by either:
- `POST /profiles/{pid}/reports/{rid}/analyze` — this endpoint does not exist (only `/reanalyze` exists)
- "backend auto-triggers analysis via a storage webhook" — webhook mechanism unspecified

**Either add the `/analyze` endpoint or specify the webhook approach.**

### 2.8 `pending_profile_update` flow incomplete (MEDIUM)

MEMORY_SYSTEM.md Section 9 describes a confirmation flow where Tier 2 extractions that imply Tier 1 changes require user approval. But:
- No API endpoint to list pending profile updates
- No API endpoint to approve/reject them
- No `pending_profile_update` in the action_log type table
- No mobile UI flow described

This is a core safety feature (preventing LLM hallucinations from corrupting structured profiles). Needs full spec.

### 2.9 CheckInConfig storage (LOW)

DIAGNOSIS_AGENT.md defines `CheckInConfig` (enabled, reminder hours, auto-abandon days) but there's no `settings` or `preferences` table in the DB schema, and no API endpoint to manage per-profile settings.

### 2.10 Environment variables list (LOW)

No document provides a complete list of required env vars. From reading all docs, the list includes at minimum:
- `PG_HOST`, `PG_PORT`, `PG_USER`, `PG_PASSWORD`
- `GEMINI_API_KEY`
- `QWEN_API_KEY`, `QWEN_BASE_URL`
- `OPENAI_API_KEY` (for embeddings)
- `NEO4J_URL`, `NEO4J_USER`, `NEO4J_PASSWORD`
- Supabase: JWT secret/JWKS URL, Storage URL, project ref

A `.env.example` template should exist.

---

## 3. Architectural Decisions to Revisit

### 3.1 ~~Three API vendors for LLM/embeddings~~ ✅ RESOLVED

Now: Cerebras (primary text tasks) + Gemini (reports, multimodal, embeddings) + Qwen (fallback). No OpenAI dependency. Embeddings use Gemini (`gemini-embedding-001`).

### 3.2 ~~Synchronous Mem0 in async FastAPI~~ ✅ RESOLVED

All Mem0 calls wrapped in `asyncio.to_thread()` in `MemoryService`.

### 3.3 LLM-only drug interaction checking

DIAGNOSIS_AGENT.md acknowledges that drug interaction checking is purely LLM-based (no pharmacological database). LLMs can hallucinate interactions or miss real ones. The "Future Enhancement" section mentions RxNorm + DrugBank for v2.

**For v1, this is acceptable if:** (a) the disclaimer is prominent, (b) the system never _recommends_ specific drugs (it doesn't), and (c) the interaction warnings are framed as "possible" not "confirmed." All three are currently true. But document this as a known limitation in user-facing terms, not just in the design doc.

### 3.4 ~~Fragile `<diagnosis_state>` JSON extraction~~ ✅ RESOLVED

Inline tag parsing eliminated. Uses two-pass approach: agentic conversation loop (Pass 1) + separate `_extract_state()` call with JSON mode (Pass 2). No inline JSON tags.

### 3.5 ~~PUT for partial profile updates~~ ✅ RESOLVED

API_SPEC.md and ARCHITECTURE.md both use `PATCH /profiles/{pid}` for partial updates.

### 3.6 ~~Mem0 data cleanup on profile deletion~~ ✅ RESOLVED

Neo4j not in v1 (pgvector only). `delete_all(profile_id)` cleans pgvector entries. Session-level cleanup via `delete_by_source()` also implemented.

### 3.7 No rate limiting on SSE connections

API_SPEC.md defines rate limits for LLM endpoints (20 req/min), but an SSE connection holds a server thread/connection for the duration of the stream. There's no documented limit on concurrent SSE connections per account. Under load, a single user could exhaust server connections.

### 3.8 Redis in tech stack

API_SPEC.md mentions "Redis (or in-memory for dev)" for rate limiting. Redis is not in the CLAUDE.md tech stack or ARCHITECTURE.md component table. If Redis is needed for production rate limiting, add it to the stack. If not, document the in-memory alternative and its limitations (resets on deploy, no cross-instance sharing).
