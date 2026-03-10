# FamilyHealth AI

## Project Overview
A family health management platform where one account manages multiple health profiles
(self, parents, spouse, children). Each profile has segregated long-term memory.
AI-powered diagnosis, medical report analysis, and health chat.

## Tech Stack
- **Backend**: Python 3.12 + FastAPI
- **Database**: PostgreSQL 16 + pgvector extension
- **Memory Layer**: Mem0 (self-hosted, open source)
- **LLM Routing**: Env-configurable via `LLM_ROUTE_*` vars. Defaults: Cerebras for all text tasks when available, Gemini for report analysis, Qwen as fallback. Auto-fallback on provider failure.
- **LLM - Cerebras**: `gpt-oss-120b` — default for chat, diagnosis, extraction, summarization
- **LLM - Gemini**: `gemini-2.5-flash` — report analysis, multimodal (auto-routed when images present)
- **LLM - Qwen**: `qwen3.5:397b` via Ollama Cloud — fallback provider
- **Embeddings**: Google Gemini (`models/gemini-embedding-001`, 768 dims) — reuses Gemini API key
- **Frontend**: React Native (Expo SDK 54, Expo Router 6) — mobile-first
- **Auth**: Supabase Auth (handles accounts, supports Google/Apple sign-in)
- **File Storage**: Supabase Storage (medical reports + chat images)
- **Deployment**: Railway (backend) + Expo EAS (mobile)

## Architecture
- Monorepo structure: `/backend`, `/mobile`, `/shared`, `/docs`
- Backend is FastAPI with service layer pattern
- All LLM interactions go through an abstract `LLMProvider` interface with `LLMRouter` dispatcher so models are swappable
- Memory layer sits between app logic and LLM — every interaction:
  1. Loads structured profile into system prompt
  2. Agent retrieves episodic memory on demand via `search_patient_memory` tool (diagnosis) or auto-injected (chat/reports)
  3. Runs conversation
  4. Post-interaction: extracts facts → stores episodic memory

## Frontend Architecture
- **Navigation**: Drawer sidebar (Claude/ChatGPT-style), no bottom tabs
- **Header**: Custom `HeaderBar` component (not React Navigation default). All buttons via `HeaderIconButton`. Sizes from `useHeaderScale()` hook (dynamic, respects system font scale + screen width)
- **Dark mode**: `useColors()` hook returns light/dark palette based on system setting. `useShadow()` for theme-aware shadows. Bidirectional type safety in `colors.ts`
- **Styling**: Inline styles + theme constants (`Spacing`, `FontSize`, `BorderRadius`). NO NativeWind/Tailwind
- **State**: Zustand (auth, active profile with AsyncStorage persistence) + React Query (server data)
- **Icons**: `@expo/vector-icons` via centralized `components/Icon.tsx` with exported `IconName` type
- **Attachments**: `useAttachMenu()` hook for Camera/Photos/Files action sheet. Validates file type on select (rejects GIF etc.). HEIC auto-converted to JPEG. Images compressed/resized (max 1536px) before upload. `pendingAttachment` state pattern on screens
- **Message parts**: Messages persist `content_parts` JSONB (text, image, tool_call, tool_result, agent_steps, memory_context, thinking, structured_input). `ChatBubble` renders rich parts via `components/message-parts/` sub-components. Falls back to plain `content` text when no parts
- **Structured inputs**: `StructuredInputView` renders interactive questions (multiple_choice, scale, yes_no, multi_select). Interactive when unanswered on latest assistant message; completed state when answered. `onStructuredResponse` callback flows through `ConversationView` → `useConversation.doSend`
- **Image caching**: `ImagePartView` uses `expo-image` with `cachePolicy="disk"` for persistent local caching
- **Design system**: See `.interface-design/system.md` for full design system documentation
- **Key constraint**: Use `ScrollView` not `FlatList` inside formSheet modals (Expo bug)

## Code Style
- Python: Black formatter, type hints required, Pydantic for all models
- TypeScript (mobile): ESLint + Prettier, strict mode, `useColors()` not static `Colors` in components
- All API endpoints have OpenAPI docs
- Tests: pytest (backend), Jest (mobile)

## Commands
- `cd backend && uvicorn app.main:app --reload --port 8010` — run backend
- `cd mobile && npx expo start` — run mobile (Expo Go)
- `cd backend && pytest` — run backend tests
- `cd backend && black . && ruff check .` — lint backend
- `cd mobile && npx tsc --noEmit` — type check mobile

## Diagnosis Workflow
The diagnosis agent uses hypothesis-driven reasoning with structured Q&A:
- Agent forms 3-5 hypotheses from the chief complaint, asks targeted questions to confirm/eliminate
- Uses `present_question` terminal tool for structured input (multiple_choice, scale, yes_no, multi_select)
- OLDCARTS framework as coverage audit (not a rigid script), red flags as hard interrupt
- Conversation history enrichment: user messages prepend question context (`_enrich_content`); assistant messages NOT enriched (models mimic any text placed there)
- User responses include rejected options ("Does NOT have: fever, vomiting") to prevent re-asking
- Red flag pre-check strips negated symptoms ("Does NOT have:", "Not selected:") before keyword scanning
- Memory retrieval is agent-driven: `search_patient_memory` tool called on turn 1 (chief complaint) and later when clinically relevant. No auto-injection into system prompt. `ContextBuilder` called with `skip_memories=True` for diagnosis
- Assessment delivered via `present_assessment` terminal tool → `AssessmentPart` in `content_parts` → `DiagnosisReportView` card-based native UI
- `present_assessment` provides structured data (conditions, medications, self_care, tests, warnings, follow_up, sources) — eliminates separate `_extract_state()` LLM call on assessment turns
- `_format_assessment_text()` generates markdown fallback for the `content` column (backward compat, search)
- `DiagnosisState.differential_diagnoses` populated directly from tool args via `_state_from_assessment_tool()`
- `StructuredInputPart` persisted in `content_parts` for both assistant (question) and user (answer)

### Agent Web Search
- `web_search` tool with `search_type` parameter: `"general"` (DuckDuckGo primary, Tavily fallback), `"academic"` (PubMed), `"drug"` (DuckDuckGo/Tavily with drug domain whitelist)
- Domain whitelists: medical (Mayo Clinic, CDC, NIH, etc.), drug (FDA, Drugs.com, RxList)
- System prompts instruct numbered citation format (no inline links — they break mobile markdown)
- Agents can search freely throughout conversation, not just before assessment
- PubMed auto-retries with keyword extraction for long queries

### Gemini Thinking Support
- Full-stack thinking: LLM layer → AgentCore → persistence → SSE → frontend
- Dormant by default; activates when Gemini handles diagnosis (`LLM_ROUTE_DIAGNOSIS=gemini`)
- `ThinkingConfig` with automatic budget, `GeminiProvider` auto-boosts `max_output_tokens` when thinking active
- Live "Reasoning..." card during streaming, persisted collapsible `ThinkingPart` in message history
- Thinking tokens excluded from conversation history and text buffer

### Planned — next phases
- **Unified session abstraction**: ✅ Done. `title` column on `diagnosis_sessions`, `PATCH /{sid}/rename`, shared `useDeleteSession`/`useRenameSession` hooks, unified `openSessionMenu` sidebar handler, auto-title generation for diagnosis
- **Structured assessment rendering**: ✅ Done. `present_assessment` terminal tool, `AssessmentPart` schema, `DiagnosisReportView` card-based native UI, SSE `structured_assessment` event
- **Consolidated session memories**: ✅ Done. Single bullet-point narrative per session replaces per-fact extraction. `_store_session_narrative()` + `_build_session_narrative()` with LLM summarization (thinking disabled for Qwen). Delete-then-add upsert via `MemoryExtractor.store_narrative()`. Fallback builds bullets directly from structured data when LLM fails. API-layer per-turn `extract_and_store` removed (4 call sites). `close_session()` also uses narrative upsert. `CollapsibleSection` shared component for memory/thinking UI with dynamic height. Memory search tool now persists query string in results.
- **Memory quality improvements**: Agent-driven retrieval working. Remaining: empty transitional text on some turns (model behavior), legacy garbage memories need cleanup, enrichment causes occasional duplicate questions

## Critical Rules
- NEVER store raw medical data in LLM context without profile scoping
- ALWAYS include medical disclaimer text in any diagnosis/analysis output
- All profile data is encrypted at rest
- Multi-profile memory is strictly segregated — NEVER leak profile A's data into profile B's context
- Use Plan Mode before any multi-file change
- ALWAYS use `useColors()` hook in components, never static `Colors` import
- ALWAYS use `useShadow()` hook, never static `Shadow` from theme
- ALWAYS use `useHapticPress()` hook or guard haptics with `process.env.EXPO_OS === 'ios'`
- ALWAYS use `HeaderIconButton` for header buttons, never inline Pressable with hardcoded sizes
- ALWAYS use `useHeaderScale()` for header sizing, never static `Header` constants
- Chat/diagnosis endpoints use `Form()` + `File()` (multipart), NOT `json` body — tests must use `data=` not `json=`
