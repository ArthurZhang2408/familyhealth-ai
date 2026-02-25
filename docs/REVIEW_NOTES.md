# Documentation Review Notes

## Resolution Status

All items below have been reviewed and resolved. See git history for the changes applied.

---

Review of `ARCHITECTURE.md`, `API_SPEC.md`, `MEMORY_SYSTEM.md`, `DIAGNOSIS_AGENT.md`, and `CLAUDE.md`.

---

## 1. Inconsistencies Between Documents

### 1.1 Mem0 LLM provider conflict (HIGH)

ARCHITECTURE.md configures Mem0's internal LLM as **Gemini**:

```python
"llm": {"provider": "google", "config": {"model": "gemini-2.0-flash"}}
```

MEMORY_SYSTEM.md configures it as **Qwen** via OpenAI-compatible endpoint:

```python
"llm": {"provider": "openai_structured", "config": {"model": "qwen-turbo"}}
```

MEMORY_SYSTEM.md includes an explicit rationale section ("Why Qwen for Mem0's Internal LLM"). The ARCHITECTURE.md version appears outdated. **Pick one and update the other.**

### 1.2 MemoryService sync vs async (HIGH)

- ARCHITECTURE.md declares all MemoryService methods as `async def`.
- MEMORY_SYSTEM.md declares them as plain `def` (synchronous).
- Mem0's Python client is synchronous, so MEMORY_SYSTEM.md is likely correct. But calling sync code from async FastAPI blocks the event loop — see Section 3.2.

### 1.3 MemoryService.search() return type (MEDIUM)

- ARCHITECTURE.md returns the raw Mem0 result: `return self._mem0.search(...)`.
- MEMORY_SYSTEM.md unwraps it: `return result.get("results", [])`.

Downstream code (prompt assembly, retrieval pipeline) assumes a `list[dict]`, so the unwrapped version is correct. ARCHITECTURE.md needs updating.

### 1.4 Diagnosis structured output tag (HIGH)

- MEMORY_SYSTEM.md Section 5 uses `<differential>` tags with a simple array schema.
- DIAGNOSIS_AGENT.md uses `<diagnosis_state>` tags with a rich schema (phase, severity, information_gathered, etc.).

These are fundamentally different. The parsing code in DIAGNOSIS_AGENT.md references `<diagnosis_state>`. **MEMORY_SYSTEM.md's prompt template needs updating to match.**

### 1.5 DifferentialDiagnosis schema (MEDIUM)

- ARCHITECTURE.md / API_SPEC.md: `{ condition, confidence, reasoning }` (3 fields).
- DIAGNOSIS_AGENT.md: `{ condition, confidence, reasoning, action_plan, urgency }` (5 fields).

The DB stores this as JSONB so it's flexible, but the API TypeScript types and mobile app will need to agree on one schema. DIAGNOSIS_AGENT.md's richer version is more useful. **Update API_SPEC.md and ARCHITECTURE.md to include `action_plan` and `urgency`.**

### 1.6 Chat `per_page` default (LOW)

- API_SPEC.md conventions section: default `per_page` = 20.
- API_SPEC.md `GET /profiles/{pid}/chat`: default `per_page` = 50.

Intentional or oversight? If intentional, document the exception.

### 1.7 `LLMService` vs `LLMProvider` naming (LOW)

- CLAUDE.md: "All LLM interactions go through an abstract `LLMService`".
- ARCHITECTURE.md: defines `LLMProvider` (interface) + `LLMRouter` (dispatcher).

Update CLAUDE.md to use the actual names.

### 1.8 Security table formatting (LOW)

ARCHITECTURE.md Section 6 "Security Summary" table has `|-|-|-|` (3 columns) but the table only has 2 data columns. Renders incorrectly in some Markdown parsers.

---

## 2. Missing Details That Block Implementation

### 2.1 OpenAI embedding dependency undocumented (HIGH)

MEMORY_SYSTEM.md requires `OPENAI_API_KEY` for `text-embedding-3-small` embeddings. This is absent from:
- CLAUDE.md tech stack
- ARCHITECTURE.md component table
- Any environment variable listing

This is a third API vendor (alongside Gemini and Qwen) that no one would know about from reading CLAUDE.md or ARCHITECTURE.md. **Decision needed: use OpenAI embeddings, switch to Gemini embeddings (`text-embedding-004`), or use Qwen embeddings to reduce vendor count?**

### 2.2 Qwen API provider unspecified (HIGH)

No document specifies:
- Which Qwen model version (qwen-turbo, qwen-plus, qwen-max, qwen2.5-*?)
- The API provider (DashScope, Together AI, OpenRouter, self-hosted?)
- The `QWEN_BASE_URL` value
- Pricing tier considerations

This blocks anyone from setting up the dev environment.

### 2.3 Background task mechanism (HIGH)

MEMORY_SYSTEM.md says extraction is a "post-interaction background task" that "never blocks the request." No mechanism is specified. Options for FastAPI:
- `BackgroundTasks` (simple, in-process, lost on crash)
- `asyncio.create_task()` (same trade-offs)
- Celery / arq / dramatiq (reliable, needs Redis/RabbitMQ)

For a health app where losing extracted memories is tolerable (they'll be re-extracted), `BackgroundTasks` is fine for v1 — but this should be an explicit decision.

### 2.4 Neo4j deployment (MEDIUM)

ARCHITECTURE.md lists Neo4j as required infrastructure. Deployment section only mentions Railway + Expo EAS. Where does Neo4j run?
- Railway (Docker container)?
- Neo4j Aura (managed cloud)?
- Same server as PostgreSQL?

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

### 3.1 Three API vendors for LLM/embeddings

Current: Gemini (diagnosis/reports) + Qwen (chat/extraction) + OpenAI (embeddings only). Three vendors means three API keys, three billing accounts, three failure modes.

**Consider:** Gemini's `text-embedding-004` or Qwen's embedding model to eliminate the OpenAI dependency entirely. This reduces vendor count to two, which is the minimum given the Gemini/Qwen split.

### 3.2 Synchronous Mem0 in async FastAPI

Mem0's Python client is synchronous. Calling it directly from `async def` route handlers will block the event loop and kill concurrency under load. Two options:
1. Wrap every Mem0 call in `asyncio.to_thread()` / `run_in_executor()`
2. Check if Mem0 has released an async client

This is a performance-critical detail for a multi-user app. **Decide on the wrapping strategy and document it in MemoryService.**

### 3.3 LLM-only drug interaction checking

DIAGNOSIS_AGENT.md acknowledges that drug interaction checking is purely LLM-based (no pharmacological database). LLMs can hallucinate interactions or miss real ones. The "Future Enhancement" section mentions RxNorm + DrugBank for v2.

**For v1, this is acceptable if:** (a) the disclaimer is prominent, (b) the system never _recommends_ specific drugs (it doesn't), and (c) the interaction warnings are framed as "possible" not "confirmed." All three are currently true. But document this as a known limitation in user-facing terms, not just in the design doc.

### 3.4 Fragile `<diagnosis_state>` JSON extraction

The system relies on the LLM emitting valid JSON inside `<diagnosis_state>` tags. The fallback on parse failure is `{"phase": "unknown", "severity": "moderate"}`, which loses the differential diagnosis.

**Consider:** Using Gemini's structured output / JSON mode (`response_mime_type: "application/json"`) and separating the conversational response from the structured data via a two-pass approach or function calling. This would be more reliable than regex-parsing embedded tags.

### 3.5 PUT for partial profile updates

API_SPEC.md uses `PUT /profiles/{pid}` but describes partial-update semantics ("only provided fields are changed"). REST convention: `PUT` = full replacement, `PATCH` = partial update. Using `PUT` with partial semantics will confuse API consumers and tools (e.g., OpenAPI generators may treat omitted fields as intentional nullification).

**Recommend:** Change to `PATCH /profiles/{pid}`.

### 3.6 Mem0 data cleanup on profile deletion

When a profile is deleted, `memory_service.delete_all(profile_id)` is called. This should clean pgvector entries, but does it also clean Neo4j graph data? Mem0's `delete_all(user_id=...)` behavior for graph stores needs verification. If it doesn't clean Neo4j, orphaned graph nodes will accumulate.

### 3.7 No rate limiting on SSE connections

API_SPEC.md defines rate limits for LLM endpoints (20 req/min), but an SSE connection holds a server thread/connection for the duration of the stream. There's no documented limit on concurrent SSE connections per account. Under load, a single user could exhaust server connections.

### 3.8 Redis in tech stack

API_SPEC.md mentions "Redis (or in-memory for dev)" for rate limiting. Redis is not in the CLAUDE.md tech stack or ARCHITECTURE.md component table. If Redis is needed for production rate limiting, add it to the stack. If not, document the in-memory alternative and its limitations (resets on deploy, no cross-instance sharing).
