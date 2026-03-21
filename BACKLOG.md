# Backlog

## Mobile — Next

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
