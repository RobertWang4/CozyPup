# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CozyPup is an AI-powered pet health assistant. Native SwiftUI iOS app + FastAPI Python backend with PostgreSQL (Neon cloud). Chat uses SSE streaming via LiteLLM (DeepSeek).

## Build & Run

### Backend

```bash
cd backend
source .venv/bin/activate
pip install -e .                              # install deps
uvicorn app.main:app --reload --port 8000     # start server
alembic upgrade head                          # apply migrations
alembic revision --autogenerate -m "msg"      # create migration
```

### iOS

```bash
cd ios-app
xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build
```

Or open `ios-app/CozyPup.xcodeproj` in Xcode and Cmd+R. Bundle ID: `com.cozypup.app`, deployment target iOS 17.0.

### Tests

```bash
cd backend && pytest tests/ -v                # all tests
cd backend && pytest tests/test_auth.py -v    # single file
```

### Debug CLI

```bash
cd backend
debug trace <correlation_id>          # inspect error snapshot
debug errors --module app.routers.pets --last 10
debug modules --since 24h             # error counts by module
debug replay <correlation_id>         # replay failed request
debug generate-test <correlation_id>  # auto-generate pytest from error
```

## Architecture

### Backend (FastAPI)

```
backend/app/
├── main.py           # App factory, middleware & router registration
├── config.py         # pydantic-settings from .env
├── auth.py           # JWT create/verify, Apple/Google OAuth, get_current_user_id dependency
├── database.py       # AsyncEngine + async_session + get_db dependency
├── models.py         # All SQLAlchemy models (User, Pet, ChatSession, Chat, CalendarEvent, Reminder, DeviceToken)
├── routers/          # One file per resource, all use get_current_user_id for auth
├── schemas/          # Pydantic request/response models per router
├── agents/           # AI agent implementations (Phase 3, not yet built)
├── middleware/        # rate_limit.py (30 msgs/hr on POST /chat)
└── debug/            # Structured JSON logging, error snapshots, CLI tools
```

**Middleware stack** (outermost first): Correlation → RequestLogging → ErrorCapture → ChatRateLimit → CORS

**Route → module mapping** in `debug/middleware.py` maps URL prefixes to source modules for error attribution. Every error response includes `correlation_id` and `src_module`.

**SSE chat format** (consumed by iOS `ChatService.swift`):
```
event: token\ndata: {"text": "..."}\n\n
event: card\ndata: {CardData JSON}\n\n
event: emergency\ndata: {"message": "...", "action": "..."}\n\n
event: done\ndata: {"intent": "chat", "session_id": "..."}\n\n
```

### iOS (SwiftUI)

```
ios-app/CozyPup/
├── CozyPupApp.swift    # Entry: auth gate → disclaimer → onboarding → ChatView
├── Services/
│   ├── APIClient.swift   # Shared actor: token management, auth fetch, SSE streaming
│   ├── ChatService.swift # SSE parser, yields SSEEvent enum
│   ├── SpeechService.swift
│   └── LocationService.swift
├── Stores/             # @MainActor ObservableObject, API-first with UserDefaults cache
│   ├── AuthStore.swift   # login() calls /auth/dev, stores JWT via APIClient
│   ├── PetStore.swift    # CRUD via /pets API, local fallback
│   ├── CalendarStore.swift
│   └── ChatStore.swift   # Message persistence, daily session reset
├── Models/             # Codable structs with snake_case CodingKeys for API compat
└── Views/              # Auth/, Chat/, Calendar/, Settings/, Cards/, Shared/
```

**APIClient** is a Swift actor that manages JWT tokens. All authenticated requests go through it. SSE streaming captures the token synchronously before creating the async stream.

**Data flow**: Stores are API-first — mutations call the backend, then update local UserDefaults cache. On failure, falls back to local-only.

## Key Design Decisions

- **Daily sessions**: One chat session per calendar day, auto-created on first message
- **Intent routing**: LLM router returns intent only (chat | summarize | map | email), no entity extraction
- **Chat Agent scope**: Handles auto-recording to calendar and calendar queries via function calling
- **pet_logs merged into calendar_events**: Added category, raw_text, edited, source fields
- **LiteLLM abstraction**: `strong_model` (deepseek/deepseek-chat) for chat, `cheap_model` (qwen/qwen-turbo) for routing
- **Dev auth**: `POST /api/v1/auth/dev` bypasses OAuth for simulator testing

## Environment

Backend `.env` requires: `DATABASE_URL` (Neon PostgreSQL), `JWT_SECRET`, `DEEPSEEK_API_KEY`. See `.env.example`.

Pet color palette (shared between backend and iOS): `["E8835C", "6BA3BE", "7BAE7F", "9B7ED8", "E8A33C"]`

## Implementation Status

- **Done**: All REST APIs (auth, pets, calendar, reminders, chat SSE, chat history, devices, rate limiting), database models, frontend-backend integration
- **Not done**: Phase 3 AI agents (emergency detection, intent router, function calling, summary/map/email agents), Phase 4 push notifications
- **Plans**: `docs/superpowers/plans/2026-03-19-backend.md` has the full task breakdown
