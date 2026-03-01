# FamilyHealth AI

## Project Overview
A family health management platform where one account manages multiple health profiles
(self, parents, spouse, children). Each profile has segregated long-term memory.
AI-powered diagnosis, medical report analysis, and health chat.

## Tech Stack
- **Backend**: Python 3.12 + FastAPI
- **Database**: PostgreSQL 16 + pgvector extension
- **Memory Layer**: Mem0 (self-hosted, open source)
- **LLM - Primary (diagnosis, reports)**: Google Gemini API (gemini-2.5-flash, gemini-2.5-flash-lite)
- **LLM - Secondary (extraction, chat)**: Qwen via Ollama Cloud (`qwen3.5:397b`)
- **Embeddings**: Google Gemini (`models/gemini-embedding-001`, 768 dims) — reuses Gemini API key
- **Frontend**: React Native (Expo SDK 54, Expo Router 6) — mobile-first
- **Auth**: Supabase Auth (handles accounts, supports Google/Apple sign-in)
- **File Storage**: Supabase Storage (medical reports)
- **Deployment**: Railway (backend) + Expo EAS (mobile)

## Architecture
- Monorepo structure: `/backend`, `/mobile`, `/shared`, `/docs`
- Backend is FastAPI with service layer pattern
- All LLM interactions go through an abstract `LLMProvider` interface with `LLMRouter` dispatcher so models are swappable
- Memory layer sits between app logic and LLM — every interaction:
  1. Loads structured profile + retrieves relevant episodic memory
  2. Injects into system prompt
  3. Runs conversation
  4. Post-interaction: extracts facts → updates profile + stores episodic memory

## Frontend Architecture
- **Navigation**: Drawer sidebar (Claude/ChatGPT-style), no bottom tabs
- **Header**: Custom `HeaderBar` component (not React Navigation default). All buttons via `HeaderIconButton`. Sizes from `useHeaderScale()` hook (dynamic, respects system font scale + screen width)
- **Dark mode**: `useColors()` hook returns light/dark palette based on system setting. `useShadow()` for theme-aware shadows. Bidirectional type safety in `colors.ts`
- **Styling**: Inline styles + theme constants (`Spacing`, `FontSize`, `BorderRadius`). NO NativeWind/Tailwind
- **State**: Zustand (auth, active profile with AsyncStorage persistence) + React Query (server data)
- **Icons**: `@expo/vector-icons` via centralized `components/Icon.tsx` with exported `IconName` type
- **Attachments**: `useAttachMenu()` hook for Camera/Photos/Files action sheet. HEIC auto-converted to JPEG. `pendingAttachment` state pattern on screens
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
