# FamilyHealth AI

## Project Overview
A family health management platform where one account manages multiple health profiles
(self, parents, spouse, children). Each profile has segregated long-term memory.
AI-powered diagnosis, medical report analysis, and health chat.

## Tech Stack
- **Backend**: Python 3.12 + FastAPI
- **Database**: PostgreSQL 16 + pgvector extension
- **Memory Layer**: Mem0 (self-hosted, open source)
- **LLM - Primary (diagnosis, reports)**: Google Gemini API (gemini-2.0-flash or gemini-2.5-pro)
- **LLM - Secondary (extraction, chat)**: Qwen via API
- **Frontend**: React Native (Expo) — mobile-first
- **Auth**: Supabase Auth (handles accounts, supports Google/Apple sign-in)
- **File Storage**: Supabase Storage (medical reports)
- **Deployment**: Railway (backend) + Expo EAS (mobile)

## Architecture
- Monorepo structure: `/backend`, `/mobile`, `/shared`, `/docs`
- Backend is FastAPI with service layer pattern
- All LLM interactions go through an abstract `LLMService` so models are swappable
- Memory layer sits between app logic and LLM — every interaction:
  1. Loads structured profile + retrieves relevant episodic memory
  2. Injects into system prompt
  3. Runs conversation
  4. Post-interaction: extracts facts → updates profile + stores episodic memory

## Code Style
- Python: Black formatter, type hints required, Pydantic for all models
- TypeScript (mobile): ESLint + Prettier, strict mode
- All API endpoints have OpenAPI docs
- Tests: pytest (backend), Jest (mobile)

## Commands
- `cd backend && uvicorn app.main:app --reload` — run backend
- `cd mobile && npx expo start` — run mobile
- `cd backend && pytest` — run backend tests
- `cd backend && black . && ruff check .` — lint backend

## Critical Rules
- NEVER store raw medical data in LLM context without profile scoping
- ALWAYS include medical disclaimer text in any diagnosis/analysis output
- All profile data is encrypted at rest
- Multi-profile memory is strictly segregated — NEVER leak profile A's data into profile B's context
- Use Plan Mode before any multi-file change