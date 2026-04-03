# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CozyPup is an AI-powered pet health assistant. Native SwiftUI iOS app + FastAPI Python backend with PostgreSQL (Neon cloud). Chat uses SSE streaming via LiteLLM (DeepSeek).

**Design Philosophy**: Interaction should be minimalist — everything AI can do, the user should NOT have to do manually. No forms, no onboarding wizards. Users talk to the AI, and the AI handles creating pet profiles, recording events, setting reminders, etc. through natural conversation.

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

Or open `ios-app/CozyPup.xcodeproj` in Xcode and Cmd+R. Bundle ID: `com.robertwang.cozypup.dev`, deployment target iOS 17.0.

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
├── agents/           # Constrained Agent framework: unified ChatAgent + validation + executor
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
event: __debug__\ndata: {trace JSON}\n\n          # only when X-Debug: true header
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
- **Unified ChatAgent**: No intent router — single ChatAgent handles all interactions (chat, summaries, emails, map search) via one LLM call with function calling
- **Constrained Agent framework**: Schema validation + ownership checks + feedback loop to minimize LLM errors without needing expensive models
- **Orchestrator + Executor**: LLM decides what to do (function calling), pure code executes it (DB writes, API calls)
- **Plan tool**: LLM calls `plan(steps=[...])` to decompose multi-step requests before executing. Orchestrator checks plan completion and nags if steps are missed. Single-step requests skip plan entirely.
- **Dual-model routing**: grok-4-1-fast for daily chat (cheap), Kimi K2.5 for emergencies (accurate). Routed via emergency keyword detection in `agents/emergency.py`
- **Debug trace**: `X-Debug: true` header activates per-request TraceCollector that records every pipeline step + parallel non-streaming LLM call for full response JSON. Emitted as `__debug__` SSE event. Zero overhead when inactive.
- **pet_logs merged into calendar_events**: Added category, raw_text, edited, source fields
- **Dev auth**: `POST /api/v1/auth/dev` bypasses OAuth for simulator testing

## Design System (MUST follow for all UI code)

Design reference: Timepage (minimalist, warm, typography-driven). All iOS UI code MUST use `Tokens.*` — never hardcode colors, fonts, or spacing.

### Colors (defined in `Theme/Tokens.swift`)

| Token | Usage |
|-------|-------|
| `Tokens.bg` | App background (warm linen) |
| `Tokens.surface` | Cards, AI bubbles |
| `Tokens.surface2` | Drawer bg, secondary surfaces |
| `Tokens.text` | Primary text |
| `Tokens.textSecondary` | Timestamps, labels |
| `Tokens.textTertiary` | Placeholders, disabled |
| `Tokens.accent` | CTA, user bubbles |
| `Tokens.accentSoft` | Accent backgrounds |
| `Tokens.green` / `Tokens.red` / `Tokens.blue` / `Tokens.orange` / `Tokens.purple` | Semantic colors |
| `Tokens.redSoft` | Error backgrounds |
| `Tokens.border` / `Tokens.divider` | Borders |
| `Tokens.white` | Text on dark/accent backgrounds (replaces `.white`) |
| `Tokens.dimOverlay` | Semi-transparent overlays (use with `.opacity()`) |
| `Tokens.placeholderBg` | Image loading placeholders |
| `Tokens.bubbleUser` / `Tokens.bubbleAi` | Chat bubble backgrounds |

Pet color palette: `["E8835C", "6BA3BE", "7BAE7F", "9B7ED8", "E8A33C"]`

### Typography

| Token | Style | Usage |
|-------|-------|-------|
| `Tokens.fontLargeTitle` | Serif .largeTitle | Login page hero title |
| `Tokens.fontTitle` / `Tokens.fontDisplay` | Serif .title2 | Section headers, calendar titles |
| `Tokens.fontHeadline` | Default .headline | Nav bar icons, button emphasis |
| `Tokens.fontBody` | Default .body | Chat messages, card content |
| `Tokens.fontCallout` | Default .callout | Secondary text slightly larger than body |
| `Tokens.fontSubheadline` | Default .subheadline | Card labels, helper text |
| `Tokens.fontCaption` | Default .caption | Timestamps, metadata |
| `Tokens.fontCaption2` | Default .caption2 | Smallest text |

Add `.weight(.semibold)` etc. as needed: `Tokens.fontBody.weight(.semibold)`

### Spacing

| Token | Value | Usage |
|-------|-------|-------|
| `Tokens.spacing.xxs` | 2pt | Tight stacking (VStack spacing between label lines) |
| `Tokens.spacing.xs` | 4pt | Inline gaps, icon padding |
| `Tokens.spacing.sm` | 8pt | Between related elements |
| `Tokens.spacing.md` | 16pt | Section padding, card insets |
| `Tokens.spacing.lg` | 24pt | Between sections |
| `Tokens.spacing.xl` | 32pt | Page-level margins |

### Component Sizes

| Token | Value | Usage |
|-------|-------|-------|
| `Tokens.size.buttonSmall` | 36pt | Send button, mic button, calendar cells |
| `Tokens.size.buttonMedium` | 44pt | Nav bar buttons (Apple HIG min touch target) |
| `Tokens.size.avatarSmall` | 32pt | Settings list icons |
| `Tokens.size.avatarMedium` | 44pt | Pet list avatars, event row height |
| `Tokens.size.avatarLarge` | 80pt | Login logo, pet edit avatar |
| `Tokens.size.iconSmall` | 28pt | Nav bar logo, edge swipe areas |
| `Tokens.size.iconMedium` | 40pt | Header action buttons |

### Radius

| Token | Value | Usage |
|-------|-------|-------|
| `Tokens.radius` | 20pt | Cards, bubbles, main containers |
| `Tokens.radiusSmall` | 12pt | Buttons, inputs, inner elements |
| `Tokens.radiusIcon` | 14pt | Icon buttons |

### iOS Code Rules

1. **MUST use `Tokens.*`** for every color, font, radius — zero hardcoded values
2. **Views never call API directly** — always go through Stores
3. **No business logic in Views** — Views only do layout + interaction
4. **Use `@ViewBuilder`** over `AnyView`
5. **Prefer `.task {}`** over `.onAppear {}` for async work
6. **Handle all states**: loading, error, empty, populated
7. **Extract reusable views** when used 2+ times (not prematurely)
8. AI-generated iOS code quality is lower than web — review more carefully
9. **All new/modified Views MUST include `#Preview`** — enables live preview in Xcode Canvas (`Option + Cmd + P`). Use mock data for pure UI components; inject mock Stores via `.environmentObject()` for pages that need them.

## Deployment

**Server**: Google Cloud Run (northamerica-northeast1 / Montreal), auto-deployed via Cloud Build on push to main.

```bash
# Auto-deploy: just push backend changes
git push origin main
# Cloud Build triggers on backend/** changes → builds Docker → deploys to Cloud Run

# Manual deploy (if needed)
cd backend
gcloud builds submit --tag northamerica-northeast1-docker.pkg.dev/cozypup-39487/cozypup/backend:latest --project=cozypup-39487
gcloud run deploy backend --image=northamerica-northeast1-docker.pkg.dev/cozypup-39487/cozypup/backend:latest --region=northamerica-northeast1 --project=cozypup-39487

# View logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=backend" --limit=20 --project=cozypup-39487

# View user login/registration events
gcloud logging read 'jsonPayload.message="user_login" OR jsonPayload.message="user_created"' --limit=10 --project=cozypup-39487

# Check service status
gcloud run services describe backend --region=northamerica-northeast1 --project=cozypup-39487
```

**Public URL**: `https://backend-601329501885.northamerica-northeast1.run.app`

> Note: Previously deployed in asia-east1 (Taiwan). Migrated to northamerica-northeast1 (Montreal) on 2026-03-28. Old asia-east1 service can be deleted.

**Avatars**: GCS bucket `cozypup-avatars` (public read)

**Secrets**: Managed via Secret Manager (DATABASE_URL, JWT_SECRET, MODEL_API_BASE, MODEL_API_KEY, GOOGLE_PLACES_API_KEY, DEEPGRAM_API_KEY)

## Environment

Backend env vars are managed via Cloud Run (secrets in Secret Manager, plain vars in service config). For local dev, use `.env` file — see `.env.example`.

## Implementation Status

- **Done**: All REST APIs, database models, iOS SwiftUI frontend, frontend-backend integration, Constrained Agent architecture, plan tool (multi-step planning), E2E audit infrastructure
- **Not done**: Phase 4 push notifications, RAG knowledge base, Phase 5 宠物共享（多主人共享 + 会员体系）
- **Spec**: `docs/superpowers/specs/2026-03-17-petcare-agent-design.md` has the full architecture (incl. design system, agent evolution roadmap, iOS standards)

## How to Add a New Tool (Checklist)

When adding a new tool to the agent, follow ALL steps below. Missing any step will cause the tool to not be called or not work correctly.

### 1. Define the tool (`backend/app/agents/tools/definitions.py`)

Add to `_BASE_TOOL_DEFINITIONS` array. The description is critical — it tells the LLM WHEN to use the tool.

```python
{
    "type": "function",
    "function": {
        "name": "my_new_tool",
        "description": (
            "一句话说明功能。\n"
            "【何时调用】具体触发场景。\n"
            "不要用于: 明确排除场景 (用 other_tool)。"
        ),
        "parameters": {
            "type": "object",
            "properties": { ... },
            "required": ["required_field"],
        },
    },
},
```

**Description 写法要求**:
- 第一行：功能概述
- 【何时调用】或【必须调用】：列出触发场景和关键词
- 不要用于：排除容易混淆的场景，指向正确的工具
- 中文写，英文翻译放 `locale.py` 的 `tool_desc_my_new_tool`

### 2. Implement the handler (`backend/app/agents/tools/`)

在对应文件里用 `@register_tool` 注册：

```python
from app.agents.tools.registry import register_tool

@register_tool("my_new_tool", accepts_kwargs=True)
async def my_new_tool(arguments: dict, db, user_id, **kwargs):
    # ... do work ...
    return {
        "success": True,
        "card": {"type": "my_card_type", ...},  # Optional: emitted to iOS
    }
```

### 3. Add validation (`backend/app/agents/validation.py`)

如果工具有枚举值或必填字段，在 `validate_tool_args` 里加校验：

```python
if name == "my_new_tool":
    if not args.get("required_field"):
        errors.append("missing required_field")
```

### 4. Update tool decision guide (`backend/app/agents/locale.py`)

在 `tool_decision_tree` 的 zh 和 en 两个版本里都加一行规则：

```
- 用户说了 XXX → my_new_tool
```

如果是**必须调用**类工具（LLM 容易跳过的），加到"关键：必须调用"列表里。

### 5. Handle in orchestrator (if special)

大部分工具不需要改 orchestrator。但如果工具需要特殊处理（如 `plan` 不走 DB，`request_images` 注入图片），在 `orchestrator.py` 的 `dispatch_tool` 里加分支。

需要用户确认的破坏性工具，加到 `agents/constants.py` 的 `CONFIRM_TOOLS` 集合里。

### 6. Add English description (`backend/app/agents/locale.py`)

在 `_STRINGS` 里加 `tool_desc_my_new_tool` 的英文翻译。

### 7. Update TEST_PLAN + add test case

- `backend/tests/e2e/TEST_PLAN.md` — 加测试用例
- `backend/tests/e2e/test_messages.py` — 加中英文测试消息
- `backend/tests/e2e/run_audit.py` — 在 `build_test_cases()` 里加 case

### 8. Run E2E audit to verify

```bash
cd backend
uvicorn app.main:app --port 8000 &
python tests/e2e/run_audit.py --lang zh --case X.X   # single case
python tests/e2e/run_audit.py --lang zh               # full audit
```

### Common Pitfalls

- **Description 太弱** → LLM 不调。用"必须调用"、列出触发关键词、用排除法
- **没加到 locale 的 decision tree** → LLM 有工具但不知道什么时候用
- **枚举值不一致** → definitions.py 里的 enum 和 validation.py 里的 set 必须一致
- **忘了清 `_tool_defs_cache`** → 重启 uvicorn 即可（cache 是进程内的）
