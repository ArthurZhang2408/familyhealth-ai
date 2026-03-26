# TODOs

## P2 — Disclaimer persistence as backend content_part

**What:** Persist `done.disclaimer` as a `content_part` (`type: 'disclaimer'`) on the assistant message in the backend. Currently using a module-level `Map<string, string>` cache in `useConversation.ts` — survives navigation but not app restart.

**Why:** Medical disclaimers should be part of the conversation record, not ephemeral client state. Users who force-quit and reopen should see the disclaimer they already accepted.

**Depends on:** Adding `DISCLAIMER` to `MessagePartType` enum in `backend/app/schemas/message_parts.py`. Frontend `ChatBubble` would need a `DisclaimerPartView` renderer.

**Effort:** S (human) / S (CC)

---

## P3 — SSE stream 401 handling

**What:** Add token refresh logic to `streamMultipartRequest()` XHR codepath in `mobile/services/api.ts`. Currently only `request()` (REST calls) retries on 401.

**Why:** If a token expires mid-stream setup, the user gets a generic error instead of automatic refresh. Low likelihood since streams always start with a fresh token, but it's a completeness gap.

**Depends on:** Nothing — standalone change.

**Effort:** M (human) / S (CC)

---

## P3 — Admin cleanup for orphaned Supabase users

**What:** Backend script or endpoint to find Supabase auth users with no corresponding profiles in the DB. Handles the rare case where `DELETE /auth/account` succeeds in DB cascade but the Supabase admin API call fails.

**Why:** Operational hygiene. Orphaned Supabase users can't log in (their data is gone) but consume auth resources. Can be manually cleaned up in Supabase dashboard for now.

**Depends on:** Nothing — standalone operational script.

**Effort:** S (human) / S (CC)
