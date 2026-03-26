# Backlog

## P0 — Must fix before TestFlight

- **Account deletion**
  - Apple requires this. No endpoint, no UI currently
  - Backend: `DELETE /auth/account` — remove user from Supabase + cascade all data (profiles, sessions, memories)
  - Frontend: Settings screen button with confirmation dialog
  - Files: `settings.tsx:104-120`, `services/auth.ts`
- **Terms of Service / Privacy Policy**
  - UI exists in settings (`settings.tsx:114-116`) but `onPress` handlers are empty `() => {}`
  - Need hosted pages (even simple web pages) and wire up the links
  - Apple reviews these for health apps
- **Medical disclaimer persistence**
  - Disclaimer is `useState` in `useConversation.ts:56` — lost on navigation
  - Backend sends it in every `done` SSE event but it's not stored
  - Fix: persist as `content_part` (`type: 'disclaimer'`) on the assistant message in backend, render from message history
  - Quicker alternative: cache in React Query keyed by session ID

## P1 — Should fix before TestFlight

- **Offline handling**
  - Zero network detection — no `NetInfo`, no connectivity checks
  - API calls fail silently or show cryptic errors; streaming hangs
  - Fix: add `@react-native-community/netinfo`, show banner when offline, disable send button
- **Screen-level error boundary**
  - `PartErrorBoundary` in `ChatBubble.tsx:32-36` catches message rendering crashes only
  - Screen-level crash (bad API data, unexpected null) white-screens the app
  - Need root `ErrorBoundary` wrapping the main layout
- **401 re-auth handling**
  - `services/api.ts` calls `supabase.auth.getSession()` per request but if session truly expires, user gets generic error instead of redirect to login
- **Auth loading flash**
  - `AuthGuard` in `_layout.tsx:31-50` returns `null` during auth check — brief white flash between splash and first screen
  - Should show branded loading state or extend splash

## P2 — Polish for good first impression

- **Chat vs diagnosis explainer**
  - `ModeToggle` switches icons with no explanation. New testers won't know what diagnosis mode does
  - Options: first-time tooltip, brief modal on first toggle, or richer subtitle
- **In-app feedback mechanism**
  - TestFlight has built-in screenshot feedback but in-app path is better
  - Options: Settings → "Send Feedback" with email compose/form, shake-to-report using existing `logger.reportToServer()`
- **Version display from build**
  - `settings.tsx:110` hardcodes `"1.0.0"` — should read from `expo-constants` so TestFlight builds are distinguishable
- **Gemini LLM timeout**
  - `llm_gemini.py:34` — Google `genai.Client` has no explicit timeout. If Gemini hangs, request blocks indefinitely
  - Other providers have timeouts (web search: 10s, reports: 60s). Wrap in `asyncio.wait_for()`
- **Prod health endpoint**
  - `/health` returns `{"status": "ok"}` but doesn't check LLM providers or database connectivity
  - Build `/debug/status` for prod LLM + search provider availability

## P3 — Nice to have

- **Auto-login after signup** — currently redirects to login screen requiring re-entry
- **Profile creation progress indicator** — 5-step wizard with no visible step dots or progress bar
- **Branded loading states** — home screen hydration shows bare `ActivityIndicator`, could use animated icon or skeleton
- **Session title generation verification** — Qwen thinking model constraints may cause issues under real load

## Mobile — Feature work

- **Prompt suggestions in chat/diagnosis screens**
  - `useChatSuggestions(conversationId)` — follow-up suggestions after assistant responds
  - `useDiagnosisSuggestions(sessionId, phase)` — post-assessment follow-ups
  - `PromptSuggestions` component already reusable, just need new data hooks
- **Memory-enhanced suggestions**
  - Backend endpoint `GET /profiles/{pid}/memory-topics?limit=3` for recent health topics
  - Add as highest-priority tier in suggestion engine after incomplete sessions
- **Title generation unification**
  - Consolidate `_auto_generate_topic` (chat) and `_auto_generate_title` (diagnosis) into shared utility
  - Prefer diagnosis's approach (more structured)
- **Screen-to-screen navigation transitions**
  - Stack/Drawer defaults are unanimated. Add spring-based slide transitions
- **Report upload flow**
  - Progress indicator during upload
  - Poll for analysis completion (`status: processing → complete`)
- **Search optimization**
  - Shared httpx client for search providers at scale

## Backend

- **Assessment warnings robustness**
  - LLM sometimes returns warnings as dicts — coerced to strings in PR #38, but could add schema-level handling

## Shipped (reference)

- ✅ PR #42 — Animated Salk icon (entrance + breathing loop + gradient rotation), branding pass (login, sidebar, headers, streaming indicator), reports hidden behind devMode
- ✅ PR #41 — Prompt suggestions (dynamic, profile-aware), pain slider (gesture-driven), confidence rings (animated SVG), profile-aware greeting, unicode fix
- ✅ PR #39 — Salk rebrand
- ✅ PR #38 — Agent steps UI redesign
- ✅ PR #37 — Context menu + session list
