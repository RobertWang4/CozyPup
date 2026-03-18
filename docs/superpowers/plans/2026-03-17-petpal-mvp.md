# PetPal MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a chat-based pet butler iOS app with AI-powered health recording, calendar, map recommendations, email generation, and push notifications.

**Architecture:** FastAPI backend with LiteLLM-powered agents (Router + 5 agents), PostgreSQL database, React + Capacitor frontend. Single chat UI with calendar/settings drawers.

**Tech Stack:** Python 3.12, FastAPI, LiteLLM, PostgreSQL, SQLAlchemy, Alembic, React 18, TypeScript, Capacitor, Vite

**Spec:** `docs/superpowers/specs/2026-03-17-petcare-agent-design.md`

---

## Phase 1: Backend Foundation

### Task 1: Project Scaffolding

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/.env.example`
- Create: `.gitignore`

- [ ] **Step 1: Initialize backend project**

```bash
mkdir -p backend/app
cd backend
```

`pyproject.toml`:
```toml
[project]
name = "petpal-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "litellm>=1.55",
    "pyjwt[crypto]>=2.9",
    "httpx>=0.28",
    "python-dotenv>=1.0",
    "pydantic-settings>=2.7",
    "sse-starlette>=2.2",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "httpx>=0.28"]
```

- [ ] **Step 2: Create config module**

`backend/app/config.py`:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/petpal"
    strong_model: str = "deepseek/deepseek-chat"
    cheap_model: str = "qwen/qwen-turbo"
    google_places_api_key: str = ""
    jwt_secret: str = "change-me-in-production"
    jwt_access_expire_minutes: int = 60
    jwt_refresh_expire_days: int = 30

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 3: Create FastAPI app entry point**

`backend/app/main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="PetPal API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Create .env.example and .gitignore**

`.env.example`:
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/petpal
STRONG_MODEL=deepseek/deepseek-chat
CHEAP_MODEL=qwen/qwen-turbo
GOOGLE_PLACES_API_KEY=
JWT_SECRET=change-me-in-production
```

`.gitignore`:
```
__pycache__/
*.pyc
.env
node_modules/
dist/
.superpowers/
*.egg-info/
.venv/
```

- [ ] **Step 5: Install dependencies and verify server starts**

```bash
cd backend && pip install -e ".[dev]"
uvicorn app.main:app --reload
# GET http://localhost:8000/health → {"status": "ok"}
```

- [ ] **Step 6: Commit**

```bash
git init
git add pyproject.toml app/ .env.example .gitignore
git commit -m "feat: initialize backend project with FastAPI"
```

---

### Task 2: Database Models + Migrations

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/models.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`

- [ ] **Step 1: Create database connection module**

`backend/app/database.py`:
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.database_url)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with async_session() as session:
        yield session
```

- [ ] **Step 2: Create all models**

`backend/app/models.py` — 7 tables per spec: users, pets, chat_sessions, chats, pet_logs, reminders, calendar_events, device_tokens.

```python
import uuid
from datetime import date, time, datetime
from sqlalchemy import String, Text, Boolean, Date, Time, ForeignKey, ARRAY, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from app.database import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    auth_provider: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    pets: Mapped[list["Pet"]] = relationship(back_populates="user", cascade="all, delete-orphan")

class Pet(Base):
    __tablename__ = "pets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    species: Mapped[str] = mapped_column(String(50), nullable=False)
    breed: Mapped[str] = mapped_column(String(100), default="")
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)
    weight: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    avatar_url: Mapped[str] = mapped_column(String(500), default="")
    color: Mapped[str] = mapped_column(String(7), default="#E8835C")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    user: Mapped["User"] = relationship(back_populates="pets")

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)

class Chat(Base):
    __tablename__ = "chats"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pet_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)

class PetLog(Base):
    __tablename__ = "pet_logs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pets.id"), nullable=False)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    pet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pets.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    trigger_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    pet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pets.id"), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    log_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pet_logs.id"), nullable=True)
    reminder_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reminders.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

class DeviceToken(Base):
    __tablename__ = "device_tokens"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(20), default="ios")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 3: Initialize Alembic and create first migration**

```bash
cd backend
alembic init alembic
```

Edit `alembic/env.py` to import `app.models` and `app.database.Base`. Edit `alembic.ini` to use `DATABASE_URL` from env.

```bash
alembic revision --autogenerate -m "create all tables"
alembic upgrade head
```

- [ ] **Step 4: Verify tables exist**

```bash
psql petpal -c "\dt"
# Should show: users, pets, chat_sessions, chats, pet_logs, reminders, calendar_events, device_tokens
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/database.py backend/app/models.py backend/alembic.ini backend/alembic/
git commit -m "feat: add database models and initial migration"
```

---

### Task 3: Auth Endpoints (Apple + Google Sign In)

**Files:**
- Create: `backend/app/auth.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/auth.py`
- Test: `backend/tests/test_auth.py`

- [ ] **Step 1: Write auth utility module**

`backend/app/auth.py` — JWT creation/verification, Apple/Google token verification via httpx.

```python
import jwt
import uuid
from datetime import datetime, timedelta
from app.config import settings

def create_access_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=settings.jwt_access_expire_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(days=settings.jwt_refresh_expire_days),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

def verify_token(token: str, expected_type: str = "access") -> dict:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Wrong token type")
    return payload

async def verify_apple_token(id_token: str) -> dict:
    """Verify Apple Sign In token. Returns {"email": ..., "sub": ...}"""
    # Decode Apple JWT, verify against Apple's public keys
    # https://developer.apple.com/documentation/sign_in_with_apple
    import httpx
    resp = await httpx.AsyncClient().get("https://appleid.apple.com/auth/keys")
    # ... verify signature, return claims
    pass

async def verify_google_token(id_token: str) -> dict:
    """Verify Google Sign In token. Returns {"email": ..., "sub": ...}"""
    import httpx
    resp = await httpx.AsyncClient().get(
        f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
    )
    return resp.json()
```

- [ ] **Step 2: Write auth router**

`backend/app/routers/auth.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.database import get_db
from app.models import User
from app.auth import (
    create_access_token, create_refresh_token,
    verify_token, verify_apple_token, verify_google_token,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

class AuthRequest(BaseModel):
    id_token: str

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/apple", response_model=AuthResponse)
async def apple_sign_in(req: AuthRequest, db: AsyncSession = Depends(get_db)):
    claims = await verify_apple_token(req.id_token)
    return await _get_or_create_user(db, claims["email"], "apple")

@router.post("/google", response_model=AuthResponse)
async def google_sign_in(req: AuthRequest, db: AsyncSession = Depends(get_db)):
    claims = await verify_google_token(req.id_token)
    return await _get_or_create_user(db, claims["email"], "google")

@router.post("/refresh", response_model=AuthResponse)
async def refresh(req: RefreshRequest):
    payload = verify_token(req.refresh_token, expected_type="refresh")
    user_id = payload["sub"]
    return AuthResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        user_id=user_id,
    )

async def _get_or_create_user(db: AsyncSession, email: str, provider: str) -> AuthResponse:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        user = User(email=email, auth_provider=provider)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    user_id = str(user.id)
    return AuthResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        user_id=user_id,
    )
```

- [ ] **Step 3: Create auth dependency for protected routes**

Add to `backend/app/auth.py`:
```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    try:
        payload = verify_token(credentials.credentials)
        return payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
```

- [ ] **Step 4: Register router in main.py**

```python
from app.routers import auth
app.include_router(auth.router)
```

- [ ] **Step 5: Write tests for JWT creation/verification**

`backend/tests/test_auth.py` — test token creation, verification, expiry, wrong type rejection.

- [ ] **Step 6: Run tests, verify pass**

```bash
cd backend && pytest tests/test_auth.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/auth.py backend/app/routers/ backend/tests/
git commit -m "feat: add auth endpoints (Apple + Google Sign In)"
```

---

### Task 4: Pets CRUD API

**Files:**
- Create: `backend/app/routers/pets.py`
- Create: `backend/app/schemas.py`
- Test: `backend/tests/test_pets.py`

- [ ] **Step 1: Write Pydantic schemas**

`backend/app/schemas.py` — PetCreate, PetUpdate, PetResponse schemas.

- [ ] **Step 2: Write pets router**

`backend/app/routers/pets.py` — CRUD: POST, GET (list), PUT, DELETE. All protected by `get_current_user_id`. Auto-assign color from palette on create.

Color palette: `["#E8835C", "#6BA3BE", "#7BAE7F", "#9B7ED8", "#E8A33C"]` — cycle through based on pet count.

- [ ] **Step 3: Write tests**

- [ ] **Step 4: Run tests, verify pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add pets CRUD API"
```

---

### Task 5: LLM Router + Emergency Detection

**Files:**
- Create: `backend/app/agents/__init__.py`
- Create: `backend/app/agents/router.py`
- Create: `backend/app/agents/emergency.py`
- Create: `backend/app/agents/prompts.py`
- Test: `backend/tests/test_router.py`
- Test: `backend/tests/test_emergency.py`

- [ ] **Step 1: Write emergency keyword detection**

`backend/app/agents/emergency.py`:
```python
EMERGENCY_KEYWORDS = [
    "seizure", "convulsion", "poison", "toxic", "choking",
    "bleeding", "blood", "collapse", "unconscious",
    "difficulty breathing", "not breathing", "swallowed",
    "hit by car", "broken bone", "fracture",
]

def detect_emergency(message: str) -> bool:
    lower = message.lower()
    return any(kw in lower for kw in EMERGENCY_KEYWORDS)
```

- [ ] **Step 2: Write prompt templates**

`backend/app/agents/prompts.py` — router prompt, chat prompt, record prompt, summary prompt, email prompt, map prompt. Each as a string template.

Router prompt should instruct the model to return JSON with `intent` and `entities`.

- [ ] **Step 3: Write LLM Router**

`backend/app/agents/router.py`:
```python
import json
import litellm
from app.config import settings
from app.agents.prompts import ROUTER_PROMPT

async def route_message(message: str, context: list[dict]) -> dict:
    """Returns {"intent": "chat"|"record"|"summarize"|"map"|"email", "entities": {...}}"""
    try:
        messages = [
            {"role": "system", "content": ROUTER_PROMPT},
            *context[-10:],  # last 10 messages
            {"role": "user", "content": message},
        ]
        response = await litellm.acompletion(
            model=settings.cheap_model,
            messages=messages,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        return {"intent": "chat", "entities": {}}
```

- [ ] **Step 4: Write tests for emergency detection**

Test with various keywords, case insensitivity, negative cases.

- [ ] **Step 5: Write tests for router** (mock LiteLLM calls)

- [ ] **Step 6: Run all tests**

```bash
pytest tests/test_router.py tests/test_emergency.py -v
```

- [ ] **Step 7: Commit**

```bash
git commit -m "feat: add LLM router and emergency detection"
```

---

### Task 6: Chat Agent (Streaming SSE)

**Files:**
- Create: `backend/app/agents/chat_agent.py`
- Create: `backend/app/routers/chat.py`
- Test: `backend/tests/test_chat.py`

- [ ] **Step 1: Write Chat Agent**

`backend/app/agents/chat_agent.py` — takes message + context + pet profiles, streams response via LiteLLM async streaming. Appends disclaimer to consultation replies.

- [ ] **Step 2: Write chat router with SSE**

`backend/app/routers/chat.py`:
- `POST /api/v1/chat` — receives message, runs emergency detection, runs router, dispatches to correct agent, streams response as SSE events (token/card/emergency/done)
- `GET /api/v1/chat/history` — paginated by session
- Manages chat_sessions (create new if none active or 30min inactive)
- Saves user message + assistant response to chats table

Use `sse-starlette` for SSE streaming.

- [ ] **Step 3: Write integration test** (mock LiteLLM, test SSE response format)

- [ ] **Step 4: Run tests**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add chat endpoint with SSE streaming"
```

---

### Task 7: Record Agent

**Files:**
- Create: `backend/app/agents/record_agent.py`
- Test: `backend/tests/test_record_agent.py`

- [ ] **Step 1: Write Record Agent**

Extracts structured data from message via cheap model. Resolves pet by name. Writes to pet_logs + calendar_events. Checks for duplicates (same pet, same date, similar category).

Returns structured card data for SSE `card` event.

- [ ] **Step 2: Write tests** (mock LLM, test DB writes, test dedup)

- [ ] **Step 3: Wire into chat router** — when intent is `record`, dispatch to record_agent

- [ ] **Step 4: Run tests**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add record agent with calendar write"
```

---

### Task 8: Summary Agent

**Files:**
- Create: `backend/app/agents/summary_agent.py`
- Test: `backend/tests/test_summary_agent.py`

- [ ] **Step 1: Write Summary Agent**

Fetches all messages in current session. Sends to cheap model for summarization. Creates pet_logs + calendar_events per extracted event. Creates reminders for items that need push notification. Dedup check against existing logs.

- [ ] **Step 2: Write tests**

- [ ] **Step 3: Wire into chat router**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: add summary agent"
```

---

### Task 9: Map Agent

**Files:**
- Create: `backend/app/agents/map_agent.py`
- Create: `backend/app/services/places.py`
- Test: `backend/tests/test_map_agent.py`

- [ ] **Step 1: Write Google Places service**

`backend/app/services/places.py` — wraps Google Places API (Nearby Search). Accepts query + coordinates. Returns list of places with name, address, rating, distance. Simple in-memory cache (TTL 2 hours).

- [ ] **Step 2: Write Map Agent**

Uses cheap model to understand user intent → builds appropriate Places API query → calls Places service → uses cheap model to organize/recommend results → returns structured map card.

- [ ] **Step 3: Write tests** (mock Places API)

- [ ] **Step 4: Wire into chat router**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add map agent with Google Places"
```

---

### Task 10: Email Agent

**Files:**
- Create: `backend/app/agents/email_agent.py`
- Test: `backend/tests/test_email_agent.py`

- [ ] **Step 1: Write Email Agent**

Gathers recent conversation context + pet profile. Uses cheap model to generate appointment email. Returns email content as structured card (type: "email").

- [ ] **Step 2: Write tests**

- [ ] **Step 3: Wire into chat router**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: add email agent"
```

---

### Task 11: Calendar + Logs + Reminders API

**Files:**
- Create: `backend/app/routers/calendar.py`
- Create: `backend/app/routers/logs.py`
- Create: `backend/app/routers/reminders.py`
- Test: `backend/tests/test_calendar.py`

- [ ] **Step 1: Write calendar router**

GET (by date range + optional pet_id), PUT (edit), DELETE. Join with pets.color for display.

- [ ] **Step 2: Write logs router**

GET (by pet_id), PUT (edit, set edited=true), DELETE.

- [ ] **Step 3: Write reminders router**

GET, PUT, DELETE.

- [ ] **Step 4: Write tests for all three**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add calendar, logs, and reminders API"
```

---

### Task 12: Push Notification Worker

**Files:**
- Create: `backend/app/routers/devices.py`
- Create: `backend/app/services/push.py`
- Create: `backend/app/worker.py`

- [ ] **Step 1: Write device token registration endpoint**

POST /api/v1/devices, DELETE /api/v1/devices/:id

- [ ] **Step 2: Write APNs push service**

`backend/app/services/push.py` — sends push via APNs HTTP/2. For MVP, can use a library like `aioapns`.

- [ ] **Step 3: Write background worker**

`backend/app/worker.py` — polls reminders table every 60s for `trigger_at <= now AND sent = false`, sends push, marks sent=true. Run as a separate process.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: add push notification worker"
```

---

### Task 13: Rate Limiting

**Files:**
- Create: `backend/app/middleware/rate_limit.py`

- [ ] **Step 1: Add rate limiting middleware**

Simple in-memory rate limiter: 30 messages per user per hour on POST /api/v1/chat. Max 2000 chars per message (validate in schema). Return 429 with Retry-After header.

- [ ] **Step 2: Commit**

```bash
git commit -m "feat: add rate limiting"
```

---

## Phase 2: Frontend

### Task 14: Frontend Project Setup

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/index.html`
- Create: `frontend/capacitor.config.ts`

- [ ] **Step 1: Initialize React + Vite + TypeScript project**

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install @capacitor/core @capacitor/cli @capacitor/ios
npm install @capacitor/keyboard @capacitor/haptics @capacitor/push-notifications
npx cap init PetPal com.petpal.app
npx cap add ios
```

- [ ] **Step 2: Set up project structure**

```
frontend/src/
├── main.tsx
├── App.tsx
├── api/            # API client
├── components/     # UI components
├── hooks/          # Custom hooks
├── stores/         # State management
├── styles/         # CSS variables + global styles
└── types/          # TypeScript types
```

- [ ] **Step 3: Create CSS theme variables**

`frontend/src/styles/theme.css` — all Warm Organic CSS variables from the demo.

- [ ] **Step 4: Create API client**

`frontend/src/api/client.ts` — axios/fetch wrapper with JWT auth, token refresh, base URL config.

- [ ] **Step 5: Verify dev server starts**

```bash
npm run dev
# http://localhost:5173 → blank app renders
```

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: initialize frontend with React + Vite + Capacitor"
```

---

### Task 15: Auth Flow (Apple + Google Sign In)

**Files:**
- Create: `frontend/src/components/LoginScreen.tsx`
- Create: `frontend/src/stores/authStore.ts`
- Create: `frontend/src/api/auth.ts`

- [ ] **Step 1: Create auth store** (token storage via Capacitor SecureStorage, login/logout/refresh logic)

- [ ] **Step 2: Create login screen** (Apple Sign In button + Google Sign In button)

- [ ] **Step 3: Create first-launch disclaimer popup**

- [ ] **Step 4: Wire into App.tsx** — show LoginScreen if no token, ChatScreen if authenticated

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add auth flow with Apple/Google Sign In"
```

---

### Task 16: Chat UI (Core)

**Files:**
- Create: `frontend/src/components/ChatScreen.tsx`
- Create: `frontend/src/components/ChatBubble.tsx`
- Create: `frontend/src/components/ChatInput.tsx`
- Create: `frontend/src/components/RecordCard.tsx`
- Create: `frontend/src/components/MapCard.tsx`
- Create: `frontend/src/components/EmailCard.tsx`
- Create: `frontend/src/components/EmergencyBanner.tsx`
- Create: `frontend/src/components/DisclaimerBar.tsx`
- Create: `frontend/src/hooks/useSSEChat.ts`

- [ ] **Step 1: Create SSE chat hook**

`useSSEChat.ts` — connects to POST /api/v1/chat via EventSource/fetch. Handles token/card/emergency/done events. Manages message list state.

- [ ] **Step 2: Create ChatBubble component** (user/assistant styles, streaming text)

- [ ] **Step 3: Create ChatInput component** (input field + mic button)

- [ ] **Step 4: Create structured card components** (RecordCard, MapCard, EmailCard)

- [ ] **Step 5: Create EmergencyBanner** (dismissible, Find button triggers map)

- [ ] **Step 6: Create DisclaimerBar** (persistent "AI suggestions are for reference only")

- [ ] **Step 7: Assemble ChatScreen** — header + emergency banner + chat stream + disclaimer + input

- [ ] **Step 8: Verify end-to-end** — send message, see streamed response, cards render

- [ ] **Step 9: Commit**

```bash
git commit -m "feat: add chat UI with SSE streaming and cards"
```

---

### Task 17: Calendar Drawer

**Files:**
- Create: `frontend/src/components/CalendarDrawer.tsx`
- Create: `frontend/src/components/CalendarGrid.tsx`
- Create: `frontend/src/components/CalendarEventList.tsx`
- Create: `frontend/src/components/CalendarEventItem.tsx`
- Create: `frontend/src/api/calendar.ts`

- [ ] **Step 1: Create CalendarGrid** — month view with colored dots per pet, today highlight, date selection

- [ ] **Step 2: Create CalendarEventList** — shows events for selected date, edit/delete buttons

- [ ] **Step 3: Create CalendarEventItem** — inline editable event card

- [ ] **Step 4: Create CalendarDrawer** — pet filter tabs + month nav + grid + event list, slides in from left

- [ ] **Step 5: Create calendar API client** (GET events, PUT edit, DELETE)

- [ ] **Step 6: Wire drawer into ChatScreen** — left icon opens, overlay closes, swipe gesture

- [ ] **Step 7: Commit**

```bash
git commit -m "feat: add calendar drawer with month view"
```

---

### Task 18: Settings Drawer

**Files:**
- Create: `frontend/src/components/SettingsDrawer.tsx`
- Create: `frontend/src/components/PetCard.tsx`
- Create: `frontend/src/components/PetForm.tsx`
- Create: `frontend/src/components/SettingsRow.tsx`
- Create: `frontend/src/components/ToggleSwitch.tsx`

- [ ] **Step 1: Create PetCard** — displays pet info with color dot and edit chevron

- [ ] **Step 2: Create PetForm** — add/edit pet modal (name, species, breed, birthday, weight, avatar)

- [ ] **Step 3: Create SettingsRow + ToggleSwitch** — reusable settings list items

- [ ] **Step 4: Create SettingsDrawer** — account card + pets section + notification toggles + legal links + logout

- [ ] **Step 5: Wire drawer into ChatScreen** — right icon opens

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: add settings drawer with pet management"
```

---

### Task 19: Push Notifications Setup

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/hooks/usePushNotifications.ts`

- [ ] **Step 1: Create push notification hook**

Register for push on app start. Send device token to backend. Handle notification received.

- [ ] **Step 2: Wire into App.tsx**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: add push notification registration"
```

---

## Phase 3: Polish + Ship

### Task 20: Compliance Features

**Files:**
- Create: `frontend/src/components/DisclaimerModal.tsx`
- Create: `frontend/src/components/ReportButton.tsx`
- Create: `frontend/src/pages/PrivacyPolicy.tsx`

- [ ] **Step 1: First-launch disclaimer modal** — must acknowledge before using

- [ ] **Step 2: Report button** — in chat, long-press message to report

- [ ] **Step 3: Privacy policy page** — accessible from settings

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: add compliance features (disclaimer, report, privacy)"
```

---

### Task 21: iOS Build + App Store Prep

**Files:**
- Modify: `frontend/capacitor.config.ts`
- Create: `frontend/ios/` (Capacitor generates)

- [ ] **Step 1: Configure Capacitor for iOS**

Set app name, bundle ID (com.petpal.app), configure deep links.

- [ ] **Step 2: Build and sync**

```bash
cd frontend
npm run build
npx cap sync ios
npx cap open ios
```

- [ ] **Step 3: In Xcode**

- Set signing team
- Configure push notification capability
- Add Apple Sign In capability
- Set app icons and launch screen

- [ ] **Step 4: Test on device/simulator**

- [ ] **Step 5: Prepare App Store Connect**

- Screenshots
- App description
- Privacy policy URL
- Data usage disclosure

- [ ] **Step 6: Submit for review**

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| Phase 1 | Tasks 1-13 | Backend: DB, auth, all agents, APIs, push, rate limiting |
| Phase 2 | Tasks 14-19 | Frontend: setup, auth, chat UI, calendar, settings, push |
| Phase 3 | Tasks 20-21 | Compliance, iOS build, App Store submission |

**Total: 21 tasks.** Backend and frontend can be developed in parallel after Task 2 (database) is complete — frontend can use mock data until backend APIs are ready.
