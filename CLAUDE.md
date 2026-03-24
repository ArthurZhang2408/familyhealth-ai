# Salk

## Project Overview
A family health management platform where one account manages multiple health profiles
(self, parents, spouse, children). Each profile has segregated long-term memory.
AI-powered diagnosis, medical report analysis, and health chat.

## Tech Stack
- **Backend**: Python 3.12 + FastAPI
- **Database**: PostgreSQL 16 + pgvector extension
- **Memory Layer**: Mem0 (self-hosted, open source)
- **LLM Routing**: Env-configurable via `LLM_ROUTE_*` vars. Defaults: Cerebras for all text tasks when available, Gemini for report analysis, Qwen as fallback. Auto-fallback on provider failure.
- **LLM - Cerebras**: `gpt-oss-120b` — default for chat, diagnosis, summarization
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
  3. Runs conversation — agent saves notable patient facts via `save_to_memory` tool
  4. Diagnosis additionally stores a consolidated narrative on assessment delivery via hard pipeline

## Frontend Architecture
- **Navigation**: Drawer sidebar (Claude/ChatGPT-style), no bottom tabs
- **Header**: Custom `HeaderBar` component (not React Navigation default). All buttons via `HeaderIconButton`. Sizes from `useHeaderScale()` hook (dynamic, respects system font scale + screen width)
- **Profile selector**: Inline dropdown from `ProfilePill` (not a formSheet). Scale-from-pill animation. Long-press context menu for edit/delete. Completeness ring (SVG) on profile avatars
- **Dark mode**: `useColors()` hook returns light/dark palette based on system setting. `useShadow()` for theme-aware shadows. Bidirectional type safety in `colors.ts`
- **Styling**: Inline styles + theme constants (`Spacing`, `FontSize`, `BorderRadius`). NO NativeWind/Tailwind
- **State**: Zustand (auth, active profile with AsyncStorage persistence + `_hydrated` flag, navigation source) + React Query (server data). All `useQuery` hooks guarded with `enabled: isAuthenticated && ...`. Profile store clears on user change via `onAuthStateChange`
- **Icons**: `@expo/vector-icons` via centralized `components/Icon.tsx` with exported `IconName` type
- **Attachments**: `useAttachMenu()` hook for Camera/Photos/Files action sheet. Validates file type on select (rejects GIF etc.). HEIC auto-converted to JPEG. Images compressed/resized (max 1536px) before upload. `pendingAttachment` state pattern on screens
- **Message parts**: Messages persist `content_parts` JSONB (text, image, tool_call, tool_result, agent_steps, memory_context, thinking, structured_input). `ChatBubble` renders rich parts via `components/message-parts/` sub-components. Falls back to plain `content` text when no parts
- **Structured inputs**: `StructuredInputView` renders interactive questions (multiple_choice, scale, yes_no, multi_select). Interactive when unanswered on latest assistant message; completed state when answered. `onStructuredResponse` callback flows through `ConversationView` → `useConversation.doSend`
- **Image caching**: `ImagePartView` uses `expo-image` with `cachePolicy="disk"` for persistent local caching
- **Animation system**: Centralized `constants/animations.ts` with spring presets (`Springs.snappy/gentle/bouncy/heavy/interactive`), timing presets (`Timings.fadeIn/fadeOut/colorShift`), layout animation factories (`enterSlideUp/Down`, `enterFade/exitFade`, `enterBounce`, `staggerDelay`). `clampedSpring()` for 0-1 progress values. Reduced motion accessibility gate via `AccessibilityInfo` listener — spring factories degrade to fade-only. `useShimmer()` hook for skeleton loading pulse. `react-native-keyboard-controller` wraps app root (`KeyboardProvider`) for frame-synced keyboard animations
- **Design system**: See `.interface-design/system.md` for full design system documentation
- **Chat FlatList**: `inverted={true}` with data reversed via `useMemo`. Conversations start at the bottom natively — no `scrollToEnd` hacks. `ListHeaderComponent` (not Footer) for streaming/typing content (header=bottom in inverted list). Streaming auto-scroll uses `scrollToOffset({ offset: 0 })`. Standard chat SDK pattern
- **ChatInput send**: Uses `onEndEditing` to accept iOS auto-correct before dispatching. `pendingSendRef` flag gates the flow: blur → iOS commits correction → `onEndEditing` provides final text → send. Falls back to direct `onSend()` when input is already blurred (`isFocused()` check)
- **List↔session slides**: `useFocusEffect` (not `useEffect`) triggers slide on every focus — Drawer keeps screens mounted. `useSharedValue(fromList ? screenWidth : 0)` initializes off-screen to prevent first-frame flash. Cleanup resets position on blur for repeat visits. `withTiming` + `Easing.out(cubic)` for ease-out curve matching sidebar feel
- **Context menu**: `ContextMenuOverlay` shared component — iOS-style BlurView overlay with full-width highlight card (title wraps up to 3 lines), `onLayout` measurement for bottom-of-screen clamping, auto-flip menu positioning, accessibility annotations. `useSessionContextMenu` hook encapsulates menu state + rename/delete mutations with error feedback and empty-name validation. Used by both sidebar and `SessionListScreen`
- **Session list screens**: `SessionListScreen` shared component — parameterized by `SessionListConfig` (type, data hook, title extractor, route, empty state). Replaces both `chat/all.tsx` and `diagnosis/all.tsx`. Includes long-press context menu, warm empty state (icon + text + action button), staggered enter animations. Empty state action uses `useNavSource.pendingMode` to pre-select mode on home screen
- **Cross-screen navigation**: `useNavSource` Zustand store (`services/navigationSource.ts`) coordinates navigation state across Drawer-mounted screens. `fromList` tracks list→session navigation for slide animations. `pendingMode` pre-selects chat/diagnosis mode on home screen. Must use store (not route params) because `useLocalSearchParams` doesn't update for Drawer routes
- **React Query invalidation**: `invalidateQueries` uses prefix matching by default — `queryKey: ['chat', pid]` matches both list AND individual queries. Use `exact: true` when only the list should refresh. On delete, use `cancelQueries` + `setQueryData(null)` instead of `removeQueries` — `removeQueries` forces mounted Drawer screens to re-create and refetch deleted items (404 spam)
- **Dev/prod mode**: `isDevMode` from `constants/config.ts` (env var `EXPO_PUBLIC_DEV_MODE=true`). Dev mode shows detailed agent step internals (tool args, thinking text, memory). Prod mode shows `StatusWordCycler` (contextual cycling phrases with pulsing dot), `LiveStreamingStatus` (unified streaming indicator with sticky-forward phase detection, elapsed timer, haptics), and `ProdAgentSummary` (capsule summary pills on persisted messages). Branching happens in `ConversationView` (ListHeaderComponent) and `ChatBubble` (AssistantBubble part rendering)
- **Prompt suggestions**: `PromptSuggestions` is a pure renderer — horizontal scrollable strip of pill-shaped chips. Accepts `suggestions: Suggestion[]` + `isLoading` + callbacks as props. Data source is the caller's responsibility (component does NOT fetch). `Suggestion` type from `services/suggestions.ts`: `{ id, type, text, icon, accent, sessionId?, sessionType? }`. Accent system: `warning` (amber, continue sessions), `success` (green, follow-ups), `primary` (blue, conditions/meds), `default` (neutral surface). Session-type suggestions (`continue`/`follow_up` with `sessionId`) route via `onNavigateSession`; all others via `onSelectPrompt`. Cross-fade animation on data change via opacity shared value. `keyboardShouldPersistTaps="always"` so chips remain tappable with keyboard open
- **Prompt suggestion data**: Home screen uses `usePromptSuggestions(mode)` hook → `buildSuggestions` engine in `services/suggestions.ts`. 6-tier priority: incomplete diagnoses → recent completed → recent chats → profile conditions → profile medications → shuffled generic pool (filtered by profile data via `needs` tags). Module-level `Map` cache keyed by `${pid}-${mode}` — persists across navigation, cleared on app restart. For chat/diagnosis screens, create NEW hooks (e.g., `useChatSuggestions`, `useDiagnosisSuggestions`) that return `Suggestion[]` from conversation context — the component is the same
- **Key constraint**: Use `ScrollView` not `FlatList` inside formSheet modals (Expo bug)

## Code Style
- Python: Black formatter, type hints required, Pydantic for all models
- TypeScript (mobile): ESLint + Prettier, strict mode, `useColors()` not static `Colors` in components
- All API endpoints have OpenAPI docs
- Tests: pytest (backend), Jest (mobile)

## Commands
- `cd backend && uvicorn app.main:app --reload --port 8010` — run backend
- `cd mobile && npx expo start` — run mobile (dev build on device; `npx expo run:ios` for first native build)
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
- Memory is fully agent-driven: `search_patient_memory` tool for retrieval (turn 1 + when clinically relevant), `save_to_memory` tool for persisting patient-stated facts. No auto-injection into system prompt. `ContextBuilder` called with `skip_memories=True` for diagnosis
- Assessment delivered via `present_assessment` terminal tool → `AssessmentPart` in `content_parts` → `DiagnosisReportView` card-based native UI
- `present_assessment` provides structured data (conditions, medications, self_care, tests, warnings, follow_up, sources) — eliminates separate `_extract_state()` LLM call on assessment turns
- `_format_assessment_text()` generates markdown fallback for the `content` column (backward compat, search)
- `DiagnosisState.differential_diagnoses` populated directly from tool args via `_state_from_assessment_tool()`
- `StructuredInputPart` persisted in `content_parts` for both assistant (question) and user (answer)

### Agent Web Search
- `web_search` tool with `search_type` parameter: `"general"` (DuckDuckGo primary, Tavily fallback), `"academic"` (PubMed), `"drug"` (DuckDuckGo/Tavily with drug domain whitelist)
- Domain whitelists: medical (Mayo Clinic, CDC, NIH, etc.), drug (FDA, Drugs.com, RxList)
- System prompts instruct numbered citation format with sources listed at the end (no inline markdown links — they break mobile markdown rendering)
- Agents can search freely throughout conversation, not just before assessment
- PubMed auto-retries with keyword extraction for long queries

### Gemini Thinking Support
- Full-stack thinking: LLM layer → AgentCore → persistence → SSE → frontend
- Dormant by default; activates when Gemini handles diagnosis (`LLM_ROUTE_DIAGNOSIS=gemini`)
- `ThinkingConfig` with automatic budget, `GeminiProvider` auto-boosts `max_output_tokens` when thinking active
- Live "Reasoning..." card during streaming, persisted collapsible `ThinkingPart` in message history
- Thinking tokens excluded from conversation history and text buffer

### Memory System (PR #30)
- **Architecture**: Agent-driven — both chat and diagnosis agents have `save_to_memory` and `search_patient_memory` tools. No post-hoc extraction pipeline. The main LLM (not a separate extraction model) decides what to persist
- **Storage**: Mem0 with pgvector backend (`health_memories` table in `mem0_db`). `add_raw(infer=False)` for all saves — bypasses Mem0's internal LLM entirely
- **Agent tools**: `save_to_memory` (write facts), `search_patient_memory` (read/search). Both injected with `profile_id` and `source` via `AgentSession.metadata`
- **Dedup**: Agent is prompted to search before saving. No embedding-based dedup (Gemini embeddings can't distinguish paraphrases from opposites)
- **Source prefixes**: `chat:{conv_id}`, `diagnosis:{session_id}:agent` (agent saves), `diagnosis:{session_id}:narrative` (hard pipeline)
- **Diagnosis hard pipeline**: `_store_session_narrative()` fires on assessment delivery. LLM summarizes user-reported facts into bullet points. Delete-then-add upsert per source. This is complementary to agent saves, not replaced by them
- **Chat**: Memory saving is purely agent-driven. System prompt instructs when to save and when not to
- **Category filter**: Mem0 pgvector only supports exact equality (`payload->>key = value`), not operator-style (`{"in": [...]}`). `MemoryService.search()` handles multi-category by searching each separately and merging by score
- **Audit trail**: `save_to_memory` handler records `memory_traces` via its own db session. Both chat and diagnosis saves are traced
- **Prompts**: `chat_prompts.py` (real chat prompt), `diagnosis_prompts.py` (diagnosis prompt). `memory_extractor.py` only has `MemoryExtractor.store_narrative()` — no prompts

### Planned — next phases
- **Unified session abstraction**: ✅ Done (PR #21)
- **Structured assessment rendering**: ✅ Done (PR #23)
- **Consolidated session memories**: ✅ Done (PR #24, reworked PR #30). Diagnosis uses hard pipeline narrative on assessment delivery + agent-driven `save_to_memory` during Q&A. Chat uses agent-driven only
- **Profile onboarding**: ✅ Done (PR #25, expanded PR #26). 5-step creation flow (identity, basics, body & lifestyle, meds & allergies, conditions + surgical history + family history), edit/delete, dropdown selector, completeness ring
- **Profile field alignment**: ✅ Done (PR #26). API returns frontend-friendly names via Pydantic `validation_alias`. Accepts both old and new names on input
- **Chat bug fixes**: ✅ Done (PR #26). `datetime` shadow import, DONE content override, diagnosis-only agent nudge, Drawer param caching
- **Stream background resilience**: ✅ Done (PR #29). Backend persists user message before LLM call. Client distinguishes background kills (XHR status 200 → "Stream interrupted") from real failures. Suppresses error UI for backgrounded/aborted streams. Typing indicator + retry polling while awaiting server response. Content-based dedup fallback for pending messages with temporary IDs
- **Agent-driven memory system**: ✅ Done (PR #30). Replaced chat's broken post-hoc nemotron extraction pipeline with agent-driven `save_to_memory` tool. Both chat and diagnosis agents decide what to persist during conversation using the main LLM. Diagnosis keeps its hard pipeline narrative (`_store_session_narrative()`) on assessment delivery. Source prefixes: `chat:{id}`, `diagnosis:{id}:agent`, `diagnosis:{id}:narrative`. Fixed Mem0 pgvector category filter (was silently broken). Agent searches before saving to prevent duplicates. Fixed chat citation format (no inline links). Solves all 10 memory extraction bugs
- **LLM tracing & debugging**: ✅ Done (PR #27). `llm_traces` table, request ID middleware, debug API, persistent file logging, client-side logger with auto-report, SSE lifecycle logging
- **Topic generation fix**: ✅ Done (PR #27). Thinking models consumed entire `max_tokens` on reasoning. Fixed via per-instance QwenProvider param routing, higher token budgets, reasoning field fallback extraction
- **Profile switch 404 fix**: ✅ Done (PR #27). Synchronous `pidChanged` guard in chat/diagnosis screens prevents stale queries when Drawer keeps screens mounted
- **Dev build migration & auth hardening**: ✅ Done (PR #28). Expo Go → dev builds (`expo-dev-client`), bundle ID `com.salk.ai`, Apple Sign In re-enabled (paid dev account). Auth guards on all query hooks, profile cleared on user change, `_hydrated` flag prevents empty-state flashes. Replaced `NoProfileGuard` + `profile-picker` with inline welcome screen. Layout clears active profile when all profiles deleted
- **Frontend UX fixes**: ✅ Done (PR #34). 429 rate limit: `RateLimitError` + `ErrorBanner` above input with countdown (replaces `Alert.alert`). Strip `[Thinking: ...]` from LLM responses at render time. Multi-select "None of the above" deselects others. Profile edit syncs Zustand `activeProfile` immediately. Backend enables `Retry-After` header (delta-seconds) + CORS expose
- **Spring animation system**: ✅ Done (PR #35). Centralized `constants/animations.ts` with 5 spring presets, 3 timing presets, layout animation factories. Migrated 15 components from hardcoded `withTiming` to spring presets. Micro-interactions: message long-press squeeze, option card scale pop, send button spring, typing dot pulse, error banner slide+shake, skeleton shimmer, collapsible section fade+chevron rotation, attachment slide-in/fade-out. `react-native-keyboard-controller` for frame-synced keyboard. ProfilePill uses clamped springs + double-tap guard. Reduced motion accessibility gate. Screen-to-screen navigation transitions NOT included (Expo Router Stack/Drawer defaults)
- **Context menu + session list**: ✅ Done (PR #37). Extracted `ContextMenuOverlay` to shared component with full-width highlight card (title wraps up to 3 lines), `onLayout` measurement for bottom-of-screen clamping, accessibility annotations. `useSessionContextMenu` hook with error feedback and empty-name validation. Unified `chat/all.tsx` and `diagnosis/all.tsx` into shared `SessionListScreen` with long-press context menu and warm empty state. `pendingMode` in `useNavSource` for Drawer cross-screen mode coordination. Fixed 404 spam: `removeQueries` → `setQueryData(null)` + `cancelQueries`, `invalidateQueries` with `exact: true`. Fixed `useDynamicFonts` double-scaling
- **Prompt suggestions + pain slider + confidence rings**: Home screen prompt suggestions (dynamic, profile-aware), pain scale slider (gesture-driven, color gradient, haptic gradient), confidence rings on diagnosis assessment (animated SVG), profile-aware greeting (`greeting()` with familiar names: Dad/Mom/Grandpa). Backend: `ensure_ascii=False` for unicode in SSE streams

### Prompt Suggestions — Future PR Roadmap
The `PromptSuggestions` component is a pure renderer (accepts `Suggestion[]` as props). The home screen data source (`usePromptSuggestions` hook + `buildSuggestions` engine) is home-specific. Future PRs need:
- **Chat suggestions (`useChatSuggestions`)**: Build `Suggestion[]` from current conversation context. Trigger: after assistant responds, suggest follow-up questions ("Ask about the medication mentioned", "Upload a lab report for context"). Place strip in `ListHeaderComponent` (bottom of inverted FlatList) or above ChatInput. Use `accent: 'default'` for all (no session navigation). Clear suggestions when user sends a message
- **Diagnosis suggestions (`useDiagnosisSuggestions`)**: Build `Suggestion[]` from diagnosis phase. Post-assessment (`phase === 'complete'`): "Start a new diagnosis", "Ask about [medication from assessment]", "Save assessment to notes". Mid-gathering: no suggestions (agent is driving Q&A). Use `accent: 'primary'` for new-session prompts, `accent: 'success'` for follow-ups
- **Memory-enhanced suggestions**: Extend `buildSuggestions` to query `search_patient_memory` for recent health topics. Requires a lightweight backend endpoint (e.g., `GET /profiles/{pid}/memory-topics?limit=3`) since memory search is server-side. Add as highest-priority tier after incomplete sessions
- **Disclaimer persistence**: Medical disclaimer currently lives in `useConversation` local state (not persisted). Navigating away loses it. Fix: persist `done.disclaimer` as a `content_part` on the assistant message in the backend, or store in React Query cache keyed by session ID

### Debugging & Logging Infrastructure (PR #27)
- **Server logs**: `logs/familyhealth.log` (RotatingFileHandler, 10MB, 5 backups). Every log line includes `request_id` for correlation
- **Request ID**: ASGI middleware assigns 12-char hex ID to every request. Available via `contextvars`, injected into all log lines, returned in `X-Request-ID` response header
- **LLM traces**: `llm_traces` table persists every LLM call (provider, model, timing, tokens, prompts, responses, fallback info). Recorded via `record_llm_traces()` after agent runs
- **Debug API** (dev-only, guarded by `app_env == "development"`):
  - `GET /debug/sessions/{id}?session_type=chat|diagnosis` — unified timeline of messages + LLM traces + memory traces
  - `GET /debug/sessions/{id}/traces` — LLM traces only (lighter)
  - `POST /debug/client-logs` — receives mobile log entries
- **Client logger** (`mobile/services/logger.ts`): Ring buffer (500 entries), categories (api/stream/auth/nav/app). `logger.reportToServer()` sends error/warn logs; failed reports queue via `pendingReport` and flush on next successful API call
- **SSE lifecycle**: Chat and diagnosis stream endpoints log duration, event count, and client disconnect detection
- **To debug a session**: `grep "REQUEST_ID" logs/familyhealth.log` or query `SELECT * FROM llm_traces WHERE session_id = '...' ORDER BY created_at`

### Thinking Model Constraints
- **Qwen3.5 on Ollama**: `think: false` parameter is broken (known Ollama bug). Thinking cannot be disabled. Must use high `max_tokens` (2000+ for simple tasks, 4000+ for complex) so thinking + answer both fit
- **Cerebras gpt-oss-120b**: `reasoning_effort: "low"` minimizes thinking but cannot fully disable it. `max_completion_tokens` includes reasoning tokens
- **QwenProvider per-instance params**: `excluded_params` (silently dropped), `promoted_params` (top-level kwargs). Cerebras excludes `enable_thinking`/`think`, promotes `reasoning_effort`. Qwen/Ollama excludes `enable_thinking`/`reasoning_effort`, passes `think` via `extra_body`
- **Reasoning fallback**: `_extract_from_reasoning()` attempts to salvage answers from the `reasoning` field when `content` is empty (looks for "Answer:"/"Topic:" markers or short last lines)

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
- ALWAYS use `!data` (not `isLoading`) to gate loading states — React Query's `isLoading` is false when queries are disabled, causing empty state flashes
- ALWAYS check `useProfileStore._hydrated` before showing empty/guard states that depend on `activeProfile` — Zustand persist hydration is async
- ALWAYS use `Springs`/`Timings` presets and layout factories from `constants/animations.ts` — never hardcode `withTiming` durations or `withSpring` configs inline
- ALWAYS use `withSequence` when chaining spring animations on the same shared value — sequential assignments cancel the previous animation
- NEVER use `scrollToEnd` on chat FlatLists — use `inverted={true}` pattern instead. For inverted lists, bottom = offset 0
- NEVER use `useEffect` for focus-dependent animations in Drawer screens — use `useFocusEffect` (Drawer keeps screens mounted, `useEffect` deps don't re-trigger)
- ChatInput send MUST go through `onEndEditing` to accept iOS auto-correct — never call `onSend()` directly from the send button when input is focused
- NEVER use `removeQueries` for queries with mounted Drawer screens — use `cancelQueries` + `setQueryData(null)` instead (removeQueries forces re-fetch → 404 spam)
- ALWAYS use `exact: true` on `invalidateQueries` when only the list query should refresh — default prefix matching also re-triggers individual item queries on mounted screens
- NEVER use `useLocalSearchParams` to pass data between Drawer-mounted screens — params don't propagate. Use `useNavSource` Zustand store instead
- NEVER use Reanimated `entering` prop for deferred visibility (hide-then-show via state) — `entering` only runs on mount, not re-renders. Use style `opacity` for deferred visibility
