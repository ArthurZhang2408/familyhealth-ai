# Backlog

## P0 — Before TestFlight (remaining)

- **Privacy Policy + Terms of Service pages** — links wired to `salk.health/privacy` and `salk.health/terms` but pages don't exist yet. Prompt file at `docs/landing-page-prompt.md`

## P2 — Polish for good first impression

- **In-app feedback mechanism**
  - TestFlight has built-in screenshot feedback but in-app path is better
  - Options: Settings → "Send Feedback" with email compose/form, shake-to-report using existing `logger.reportToServer()`
- **Prod health endpoint (full)**
  - `/health` now checks DB connectivity. Full LLM + search provider health (`/debug/status`) still deferred

## P3 — Nice to have

- **Auto-login after signup** — currently redirects to login screen requiring re-entry
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

- ✅ PR #43 — TestFlight gap fixes: account deletion (DELETE /auth/account + cascade), ToS/Privacy links (salk.health), constant medical disclaimer, 401 re-auth retry, expo-splash-screen, offline banner (netinfo), ErrorBoundary, version from expo-constants, Gemini 120s timeout, /health DB check, ModeToggle animated label, profile wizard step labels, welcome copy
- ✅ PR #42 — Animated Salk icon (entrance + breathing loop + gradient rotation), branding pass (login, sidebar, headers, streaming indicator), reports hidden behind devMode
- ✅ PR #41 — Prompt suggestions (dynamic, profile-aware), pain slider (gesture-driven), confidence rings (animated SVG), profile-aware greeting, unicode fix
- ✅ PR #39 — Salk rebrand
- ✅ PR #38 — Agent steps UI redesign
- ✅ PR #37 — Context menu + session list
