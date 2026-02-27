# Backlog

## Mobile — Next Milestone

- **Session management for Diagnosis + Chat**
  - Session list screen per feature (list past sessions, tap to resume)
  - Load conversation history from API on mount (`GET /profiles/:pid/diagnosis/:sid`, `GET /profiles/:pid/chat/:cid`)
  - Resume existing sessions instead of always creating new ones
  - Remove hardcoded first reply in diagnosis.tsx — use actual API response
- **Real-time message UX**
  - Optimistic updates for sent messages
  - Scroll-to-bottom on new messages
  - React Query cache for conversation persistence across navigation
- **Report upload flow**
  - Progress indicator during upload
  - Poll for analysis completion (`status: processing → complete`)
- **Profile editing**
  - Edit profile screen (allergies, medications, conditions, emergency contacts)
- **Error states**
  - Network error banners, retry buttons, offline detection

## Backend

- **Migrate `@app.on_event` to lifespan** (`backend/app/main.py:47,52`)
  FastAPI deprecated `@app.on_event("startup"/"shutdown")` in 0.93. Replace with a `@asynccontextmanager` lifespan function passed to `FastAPI(lifespan=...)`. No functional impact today — just a deprecation warning.
- **Remove unused `supabase_jwt_secret` config** (`backend/app/core/config.py`)
  JWT verification now uses JWKS/ES256. The HS256 secret field in config and `.env` is dead code.
