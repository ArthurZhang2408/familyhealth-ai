# Backlog

## Mobile — Next

- **Prompt suggestions in chat/diagnosis screens**
  - `useChatSuggestions(conversationId)` — follow-up suggestions after assistant responds
  - `useDiagnosisSuggestions(sessionId, phase)` — post-assessment follow-ups
  - `PromptSuggestions` component already reusable, just need new data hooks
- **Memory-enhanced suggestions**
  - Backend endpoint `GET /profiles/{pid}/memory-topics?limit=3` for recent health topics
  - Add as highest-priority tier in suggestion engine after incomplete sessions
- **Disclaimer persistence**
  - Medical disclaimer lost on navigation (lives in useConversation local state)
  - Fix: persist as `content_part` on assistant message, or React Query cache
- **Title generation unification**
  - Consolidate `_auto_generate_topic` (chat) and `_auto_generate_title` (diagnosis) into shared utility
  - Prefer diagnosis's approach (more structured)
- **Screen-to-screen navigation transitions**
  - Stack/Drawer defaults are unanimated. Add spring-based slide transitions
- **Report upload flow**
  - Progress indicator during upload
  - Poll for analysis completion (`status: processing → complete`)
- **Prod observability**
  - Build `/debug/status` endpoint for prod LLM + search health metrics
- **Search optimization**
  - Shared httpx client for search providers at scale

## Backend

- **Assessment warnings robustness**
  - LLM sometimes returns warnings as dicts — coerced to strings in PR #38, but could add schema-level handling

## Shipped (reference)

- ✅ PR #41 — Prompt suggestions (dynamic, profile-aware), pain slider (gesture-driven), confidence rings (animated SVG), profile-aware greeting, unicode fix
- ✅ PR #39 — Salk rebrand
- ✅ PR #38 — Agent steps UI redesign
- ✅ PR #37 — Context menu + session list
