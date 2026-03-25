# PetCare Agent - MVP Design Spec

## 1. Product Vision

A pet butler app with a single chat interface as the only input method. Unlike traditional pet apps that use forms and buttons, PetCare uses natural conversation to automatically build structured health calendars, provide safe pre-consultation references, and recommend nearby pet-friendly locations.

**Core insight:** The app is not a pet chatbot — it's a pet butler with memory. Chat is the input method; the calendar/timeline is where value accumulates.

## 2. Target Market

- **Initial launch:** Overseas (English-speaking markets)
- **Future:** China mainland (with localized model and map providers)
- **Target users:** General pet owners (not niche), multi-pet households supported

## 3. System Architecture

```
User Input (text + app-level speech-to-text)
    │
    ▼
┌──────────────────────────────────────────────────┐
│  FastAPI Backend                                 │
│                                                  │
│  ┌──────────────────────┐                        │
│  │ Emergency Keyword    │                        │
│  │ Detection (regex)    │                        │
│  └──────────┬───────────┘                        │
│             │ (non-blocking, emits SSE event)     │
│             ▼                                    │
│  ┌──────────────────────────────────────────┐    │
│  │ Unified ChatAgent (single LLM call)      │    │
│  │                                          │    │
│  │  ┌─────────────┐  ┌──────────────────┐   │    │
│  │  │ Streaming   │  │ Function Calling │   │    │
│  │  │ Text Output │  │ (tool_choice=auto│   │    │
│  │  └─────────────┘  └───────┬──────────┘   │    │
│  │                           │              │    │
│  │                    ┌──────▼──────┐       │    │
│  │                    │ Validation  │       │    │
│  │                    │ Layer       │       │    │
│  │                    │ - Schema    │       │    │
│  │                    │ - Ownership │       │    │
│  │                    │ - Confirm?  │       │    │
│  │                    └──────┬──────┘       │    │
│  │                           │              │    │
│  │                    ┌──────▼──────┐       │    │
│  │                    │ Executor    │       │    │
│  │                    │ (pure code, │       │    │
│  │                    │  no LLM)    │       │    │
│  │                    └─────────────┘       │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  ┌────────────────┐  ┌──────────────┐            │
│  │  PostgreSQL    │  │ Push Service │            │
│  │                │  │ (APNs)      │            │
│  └────────────────┘  └──────────────┘            │
│                                                  │
│  ┌──────────────────────────────────────────┐    │
│  │  LiteLLM (Model Abstraction Layer)       │    │
│  │  - Unified API for all LLM providers     │    │
│  │  - Single model config (swappable)       │    │
│  │  - Default: DeepSeek / MiniMax / Kimi    │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  ┌──────────────────────────────────────────┐    │
│  │  RAG Layer (future)                      │    │
│  │  - Vector DB for pet health knowledge    │    │
│  │  - User private data via tool calling    │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  ┌──────────────────────────────────────────┐    │
│  │  Map Abstraction Layer                   │    │
│  │  - Overseas: Google Places API           │    │
│  │  - China: Amap (reserved)                │    │
│  └──────────────────────────────────────────┘    │
└──────────────────────────────────────────────────┘
```

### 3.1 AI Framework

- **LiteLLM** for model abstraction — unified API across 100+ LLM providers, model switching is a config change
- **Constrained Agent framework** — single ChatAgent with validation layers to minimize LLM errors. No LangChain.
- **FastAPI** handles HTTP, streaming (SSE), and orchestration
- **Orchestrator + Executor pattern** — LLM decides *what* to do (function calling), pure code *executes* it

### 3.2 Model Configuration

Single model for all tasks. The Constrained Agent framework compensates for model limitations through validation, making cheaper models viable.

| Market | Default Model | Alternatives |
|--------|--------------|-------------|
| Overseas | DeepSeek-V3.2 | MiniMax M2.7, Kimi K2.5, GPT-5.4-mini |
| China (future) | DeepSeek-V3.2 | MiniMax M2.7, Qwen-Plus |

Model selection criteria: function calling accuracy > generation quality > price. Framework validation catches most errors, so mid-tier models suffice.

### 3.3 Map Abstraction Layer

| Market | Provider | Cost |
|--------|----------|------|
| Overseas | Google Places API + cache | ~$150/mo per 1K users |
| China (future) | Amap (高德) | ¥50,000/yr base |

Cache strategy: same-area results cached for a few hours to reduce API calls.

### 3.4 RAG Layer (future)

Two-tier knowledge augmentation:

1. **General knowledge base** — pet health encyclopedia, breed care guides, vaccination schedules, medication info. Embedded in vector DB, top-k results injected into system prompt at query time.
2. **User private data** — already implemented via function calling tools (`query_calendar_events`, `list_pets`, pet profile JSON). This is structured RAG through direct DB queries.

RAG improves answer quality (knowledge). It does NOT improve agent execution accuracy (tool calling) — that is handled by the Constrained Agent framework.

## 4. Agent Design

### 4.1 Design Philosophy: Constrained Agent

**Previous design (deprecated):** LLM Router → 4 separate agents (Chat, Summary, Map, Email), each with its own model. Problems: router adds latency + cost, intent boundaries are fuzzy, maintenance overhead of 5 prompt templates.

**Current design:** Single unified ChatAgent handles all interactions — chat, summaries, email drafts, map searches — via one LLM call with function calling. Error prevention is handled by framework validation layers, not by splitting into sub-agents.

**Core principle: minimize the decision space the LLM operates in.** The less freedom the model has, the fewer mistakes it makes.

### 4.2 Unified ChatAgent

One agent handles everything:
- General conversation, health consultation, daily chat
- Summarizing conversation history (via prompt, not separate agent)
- Drafting vet emails (via prompt, not separate agent)
- Finding nearby locations (via `search_places` tool)
- Recording events, creating pets, setting reminders (via function calling)

Rules:
- No diagnosis, no prescriptions, reference only
- Every consultation reply ends with disclaimer
- Streaming response via SSE
- Must respond in the same language the user uses

### 4.3 Function Calling Tools

The ChatAgent has access to these tools. The LLM decides when to call them; the Executor handles DB writes.

| Tool | Purpose | Returns Card? |
|------|---------|--------------|
| `create_calendar_event` | Record health events to calendar | Yes (record card) |
| `query_calendar_events` | Look up past events/history | No |
| `create_pet` | Add a new pet profile (auto-generates initial profile_md) | Yes (pet_created card) |
| `update_pet_profile` | Save any pet info as flexible key-value JSON | No |
| `save_pet_profile_md` | Silently update pet's narrative markdown profile when learning new info from chat | No |
| `summarize_pet_profile` | User-triggered: comprehensively summarize and update pet profile from chat history | Yes (profile_summarized card) |
| `list_pets` | List all registered pets with IDs | No |
| `create_reminder` | Set push notification reminder | Yes (reminder card) |
| `search_places` | Find nearby vets, parks, pet stores via Google Places API | Yes (map card) |
| `draft_email` | Generate vet appointment email from conversation context | Yes (email card) |

### 4.4 Constrained Agent Framework (Validation Layers)

When the LLM returns a tool call, it passes through validation before execution:

```
LLM returns tool_call
    │
    ▼
┌─ Schema Validation ─────────────────────────────┐
│ - Required fields present?                       │
│ - Date format valid? (YYYY-MM-DD)                │
│ - Category in enum?                              │
│ - JSON parseable?                                │
│ → On failure: feed error back to LLM for retry   │
└──────────────────────────────────────────────────┘
    │
    ▼
┌─ Ownership Validation ──────────────────────────┐
│ - pet_id belongs to this user?                   │
│ - pet_id exists in DB?                           │
│ → On failure: feed error back to LLM for retry   │
└──────────────────────────────────────────────────┘
    │
    ▼
┌─ Confirmation Gate (high-risk ops only) ────────┐
│ - create_pet → emit confirm card, wait for user  │
│ - create_calendar_event → execute immediately     │
│   (low risk, user sees record card as feedback)   │
│ → On deny: inform LLM that user declined          │
└──────────────────────────────────────────────────┘
    │
    ▼
┌─ Executor ──────────────────────────────────────┐
│ - Pure code, no LLM calls                        │
│ - Writes to DB, calls external APIs              │
│ - Returns structured result + optional card data │
└──────────────────────────────────────────────────┘
    │
    ▼
┌─ Feedback Loop ─────────────────────────────────┐
│ - Tool result fed back to LLM                    │
│ - LLM generates natural language confirmation    │
│ - User sees both the card AND the text response  │
└──────────────────────────────────────────────────┘
```

This framework catches ~70% of potential agent errors (invalid params, hallucinated IDs, wrong formats) without requiring a smarter model.

Max tool call rounds per message: 5 (prevents infinite loops).

### 4.5 Context Injection

To reduce LLM guessing (and thus errors), the system prompt is pre-loaded with:

- **Pet list with IDs** — LLM doesn't need to guess or hallucinate pet_id
- **Today's date** — LLM doesn't need to guess the current date
- **Pet profile JSON** — breed, weight, allergies, diet, medical history
- **Recent calendar events** — accessible via `query_calendar_events` tool
- **Recent conversation history** — last 20 messages from current session

### 4.6 Multi-Pet Resolution

The ChatAgent identifies which pet the user is talking about:
1. Explicit name match ("Doudu is sick" → Doudu)
2. Context inference (if user only has one pet, default to it)
3. If a single message mentions multiple pets, create separate entries per pet
4. Ambiguous → agent asks "Which pet are you referring to?"

### 4.7 Emergency Detection

Runs before the ChatAgent, zero-cost:
1. Regex keyword detection (seizure, poison, choking, bleeding, etc.)
2. If triggered: emit `emergency` SSE event (non-blocking banner)
3. ChatAgent still processes the message normally
4. Future: ChatAgent can also trigger emergency via tool if it detects dangerous symptom combinations not covered by keywords

## 5. Database Schema

All tables include `updated_at TIMESTAMP` (auto-updated on modification) in addition to `created_at`.

### users
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| email | VARCHAR | Login email |
| auth_provider | VARCHAR | apple / google |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### pets
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID | FK → users |
| name | VARCHAR | Pet name |
| species | VARCHAR | cat / dog / other |
| breed | VARCHAR | Breed |
| birthday | DATE | Optional, for age calculation |
| weight | DECIMAL | Optional, health reference |
| avatar_url | VARCHAR | Avatar |
| color | VARCHAR | Display color for calendar (auto-assigned) |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### chat_sessions
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID | FK → users |
| started_at | TIMESTAMP | Session start |
| ended_at | TIMESTAMP | Nullable, set when session closes |

One session per calendar day, auto-created. If no session exists for today, a new one is created when the user sends a message.

### chats
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| session_id | UUID | FK → chat_sessions |
| user_id | UUID | FK → users |
| role | VARCHAR | user / assistant |
| content | TEXT | Message content |
| created_at | TIMESTAMP | |

### reminders
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID | FK → users |
| pet_id | UUID | FK → pets |
| type | VARCHAR | scheduled / insight |
| title | VARCHAR | Push title |
| body | TEXT | Push content |
| trigger_at | TIMESTAMP | When to push |
| sent | BOOLEAN | Whether sent |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### calendar_events
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID | FK → users |
| pet_id | UUID | FK → pets |
| event_date | DATE | Date |
| event_time | TIME | Optional |
| title | VARCHAR | Event title |
| type | VARCHAR | log / appointment / reminder |
| category | VARCHAR | diet / excretion / abnormal / vaccine / deworming / medical / daily |
| raw_text | TEXT | Original input or conversation excerpt |
| source | VARCHAR | chat / manual |
| edited | BOOLEAN | Whether manually edited by user |
| reminder_id | UUID | FK → reminders (optional) |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

Color is derived from `pets.color`, not stored on calendar_events.

### device_tokens
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID | FK → users |
| token | VARCHAR | APNs device token |
| platform | VARCHAR | ios |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

## 6. API Design

### Authentication

JWT-based. Access token (short-lived, 1h) + refresh token (long-lived, 30d). Stored in Capacitor Secure Storage (iOS Keychain). Passed via `Authorization: Bearer <token>` header.

```
POST   /api/v1/auth/apple       Apple Sign In → returns JWT pair
POST   /api/v1/auth/google      Google Sign In → returns JWT pair
POST   /api/v1/auth/refresh     Refresh access token
```

### Pets
```
POST   /api/v1/pets             Add pet
GET    /api/v1/pets             List user's pets
PUT    /api/v1/pets/:id         Edit pet info
DELETE /api/v1/pets/:id         Delete pet
```

### Chat (core)
```
POST   /api/v1/chat             Send message (SSE streaming response)
GET    /api/v1/chat/history     Get chat history (paginated by session)
```

**POST /api/v1/chat response format (SSE):**
```
event: token
data: {"text": "Your dog might be..."}

event: token
data: {"text": " experiencing mild..."}

event: card
data: {"type": "record", "pet_name": "Doudu", "date": "2026-03-17", "category": "abnormal"}

event: emergency
data: {"message": "Possible emergency detected", "action": "find_er"}

event: done
data: {"intent": "chat", "session_id": "..."}
```

Frontend renders different components based on event type: `token` → append to chat bubble, `card` → render structured card, `emergency` → show banner, `done` → end stream.

### Calendar
```
GET    /api/v1/calendar         Get events (by date range + optional pet_id filter)
PUT    /api/v1/calendar/:id     Edit calendar entry
DELETE /api/v1/calendar/:id     Delete calendar entry
```

### Reminders
```
GET    /api/v1/reminders        List reminders
PUT    /api/v1/reminders/:id    Edit reminder
DELETE /api/v1/reminders/:id    Delete reminder
```

### Push Notifications
```
POST   /api/v1/devices          Register device token
DELETE /api/v1/devices/:id      Unregister device token
```

A background worker (async task or cron) polls `reminders` table for `trigger_at <= now AND sent = false`, sends via APNs, and marks `sent = true`.

### Rate Limiting

- 30 messages per user per hour
- Max 2000 characters per message
- Rate limit headers returned in response

Write operations (creating logs, calendar events, reminders) are handled by AI agents through the `/chat` endpoint. Manual editing uses PUT/DELETE endpoints.

## 7. Frontend Design

### Tech Stack
- Native SwiftUI (iOS 17+), MVVM architecture
- Single-screen chat-centric UI

### Page Structure

```
┌──────────────────────────────┐
│ 📅                        ⚙️ │
│                              │
│       Chat Stream            │
│                              │
│   ┌──────────────────────┐   │
│   │ AI建议仅供参考        │   │
│   └──────────────────────┘   │
│                              │
│  ┌────────────────────────┐  │
│  │  Type a message...  🎤 │  │
│  └────────────────────────┘  │
└──────────────────────────────┘

← Left: Calendar drawer    Right: Settings drawer →
```

- **Left icon:** Tap or swipe left → calendar drawer
  - Month view with colored dots per pet
  - Tap date → expand day's events
  - Events are editable/deletable inline
  - Filter by pet at top
- **Right icon:** Tap or swipe right → settings drawer
  - Pet management (add/edit/delete pets)
  - Account info
  - Notification settings
  - Privacy policy / disclaimer
  - Logout
- **No bottom tabs, no pet switcher** — AI infers which pet from conversation context
- **Voice input:** Native SFSpeechRecognizer, converted to text and inserted into input field

### Chat UI Elements
- Standard chat bubbles for user/assistant (streamed via SSE)
- Structured cards embedded in AI replies (health record confirmation, map recommendations, email drafts)
- Emergency prompt banner (non-blocking, dismissible)

### Location Handling
- Location permission requested on-demand (first time user asks for nearby places)
- Frontend sends GPS coordinates with the chat message when available
- Fallback: if no location available, ChatAgent asks user to share location or enter an address

## 8. Emergency Prompt (Non-Blocking)

**Not an intercept — a suggestion.**

1. Regex keyword detection runs before ChatAgent (seizure, poison, choking, bleeding, difficulty breathing, collapse, etc.)
2. If triggered: AI responds normally + a dismissible banner appears:
   > "Detected a possible emergency. Want to find a nearby 24-hour pet ER?"
3. User taps "Find" → ChatAgent calls `search_places` tool for emergency vet clinics
4. User dismisses → continues chatting normally

No conversation interruption. No forced behavior.

## 9. App Store Compliance

1. **Persistent disclaimer bar** in chat: "AI suggestions are for reference only"
2. **Chat Agent forced suffix:** Every consultation reply ends with "The above is for reference only, please consult a professional veterinarian"
3. **First-launch disclaimer popup** — user must acknowledge before using
4. **Privacy policy page** — accessible from settings
5. **Data collection disclosure** — OAuth info, chat content, location data
6. **AI content labeling** — mark AI-generated content
7. **Report button** — Apple requires reporting mechanism for AI/UGC content

## 10. Cost Estimate

Per 1,000 monthly active users, 5 interactions/day. Single model (no router overhead):

| Component | Monthly Cost |
|-----------|-------------|
| DeepSeek-V3.2 (unified ChatAgent) | ~$50 |
| Google Places API (with cache) | ~$160 |
| PostgreSQL (Neon cloud) | ~$20 |
| APNs push | $0 |
| **Total** | **~$230/month** |

Model abstraction layer (LiteLLM) allows swapping to any provider with a config change. If function calling accuracy requires a stronger model (e.g., MiniMax M2.7 at ~$80/mo or Kimi K2.5 at ~$120/mo), the Constrained Agent framework keeps total cost manageable.

## 11. Out of Scope for MVP

- RAG / vector search (planned for post-MVP, see Section 3.4)
- Social features
- Amap integration (reserved in abstraction layer)
- Pet health report generation
- Data export
- Confirmation gate for tool calls (v1 executes immediately, shows card as feedback)

## 12. Design System

Inspired by the "design system in Claude Code" approach — all design tokens are defined once and enforced everywhere. AI-generated UI code must follow this system, ensuring visual consistency without manual review of every screen.

**Design reference:** Timepage (calendar app) — minimalist, warm, typography-driven.

### 12.1 Color Palette

| Token | Hex | Usage |
|-------|-----|-------|
| `bg` | F5EBE0 | App background (warm linen) |
| `surface` | FBF6F1 | Cards, AI bubbles (warm off-white) |
| `surface2` | F5ECE3 | Secondary surfaces, drawer bg |
| `text` | 3D2C1E | Primary text (dark brown) |
| `textSecondary` | 8B7355 | Timestamps, labels |
| `textTertiary` | B8A48E | Placeholders, disabled text |
| `accent` | E8835C | Primary action, user bubbles, CTA |
| `accentSoft` | F0DDD3 | Accent backgrounds, hover states |
| `green` | 7BAE7F | Success, active switches |
| `blue` | 6BA3BE | Info, links |
| `red` | D35F5F | Errors, emergency |
| `redSoft` | F5E2DC | Error backgrounds |
| `orange` | E8A33C | Warnings |
| `purple` | 9B7ED8 | Highlights |
| `border` | E6D5C5 | Borders, dividers |

**Pet palette** (auto-assigned per pet, for calendar dots and cards):
`["E8835C", "6BA3BE", "7BAE7F", "9B7ED8", "E8A33C"]`

### 12.2 Typography

| Level | Font | Size | Weight | Usage |
|-------|------|------|--------|-------|
| Display | System Serif | .title2 | Regular | Calendar headers, section titles |
| Body | System Default | .body | Regular | Chat messages, card content |
| Caption | System Default | .caption | Regular | Timestamps, metadata, labels |
| Button | System Default | .body | Semibold | Button labels, CTAs |

**Rules:**
- Never use more than 3 font sizes on a single screen
- Serif display font only for decorative/header elements, never for body text
- Chinese and English text must use the same font tokens (system font handles both)

### 12.3 Spacing & Layout

| Token | Value | Usage |
|-------|-------|-------|
| `radius` | 20pt | Cards, bubbles, main containers |
| `radiusSmall` | 12pt | Buttons, input fields, inner elements |
| `radiusIcon` | 14pt | Icon buttons, small interactive elements |
| `spacing.xs` | 4pt | Inline element gaps |
| `spacing.sm` | 8pt | Between related elements |
| `spacing.md` | 16pt | Section padding, card insets |
| `spacing.lg` | 24pt | Between sections |
| `spacing.xl` | 32pt | Page-level margins |

**Rules:**
- All cards use `radius` (20pt) with `surface` background
- Horizontal page padding is always `spacing.md` (16pt)
- Chat bubbles have 12pt internal padding, 8pt vertical gap between messages

### 12.4 Component Patterns

| Component | Background | Corner Radius | Shadow |
|-----------|-----------|---------------|--------|
| Chat bubble (user) | `accent` | `radius` | None |
| Chat bubble (AI) | `surface` | `radius` | None |
| Action card | `surface` | `radius` | Subtle (0.5pt, 5% opacity) |
| Input bar | `surface` | `radiusSmall` | None |
| Emergency banner | `red` | `radiusSmall` | None |
| Calendar day cell | transparent | Circle | None |
| Drawer | `surface2` | `radius` (top corners only) |  None |

### 12.5 Animation & Interaction

- Drawer open/close: 0.3s ease-in-out spring animation
- Card appearance: fade-in 0.2s
- Typing indicator: 3 dots with staggered 0.4s bounce
- No unnecessary animations — every animation must serve a functional purpose
- Haptic feedback on key actions (send message, card tap, drawer open)

## 13. Agent Architecture Evolution Roadmap

Inspired by the three-phase agent evolution model. CozyPup is currently between Phase 1 and Phase 2; the roadmap below charts the path forward.

### Phase 1: Intent Parser + Code Executor (Current — Constrained Agent v1)

```
User Message → Pre-processor (regex intent) → LLM (single call, function calling) → Validation → Executor → Card
```

**Characteristics:**
- Single LLM call per user message
- Pre-processor does regex-based intent detection
- Post-processor catches missed tool calls
- All tool execution is deterministic code (no LLM in executor)

**Limitation:** Cannot handle multi-step requests ("帮我安排下周的疫苗接种，创建日历事件，然后设个提醒"). LLM must complete everything in one round of function calling.

### Phase 2: Multi-Step Execution (Next — Constrained Agent v2)

```
User Message → Pre-processor → LLM Call 1 (tool call) → Validate + Execute → Feed result back → LLM Call 2 (next tool) → ... → Final response
```

**What changes:**
- Allow the LLM to make sequential tool calls across multiple rounds (current max_rounds=5 already supports this, but prompting and flow need optimization)
- Improve system prompt to encourage step-by-step tool usage for complex requests
- Track "plan state" within a single message: which steps are done, which remain
- Pre-processor suggests a multi-step plan for complex requests (e.g., detect "vaccine + reminder" pattern → suggest [create_calendar_event, create_reminder])

**What stays the same:**
- Still a single ChatAgent, no sub-agents
- Validation + executor pattern unchanged
- No additional LLM calls for planning (the chat LLM itself handles sequencing)

### Phase 3: Planning Pipeline (Future — when complexity demands it)

```
User Message → Planner LLM → Step list → Execute step 1 → Execute step 2 → ... → Assembler → Response
```

**When to adopt:** Only when Phase 2 fails to handle common multi-step requests reliably. Signs: frequent partial completions, tool calls in wrong order, context loss between steps.

**What changes:**
- Dedicated planning step before execution
- Step decomposition with dependency tracking
- Model-unified coordination (same model for planning and execution, different prompts)
- Self-validation flywheel: verify each step's output before proceeding to next

**Key principle:** Don't move to Phase 3 prematurely. Per the "让它 work 就可以" philosophy — complexity should be added only when simpler approaches fail.

## 14. iOS Code Quality Standards

AI-generated iOS code quality lags behind web code. These standards compensate:

### 14.1 Architecture Rules
- **MVVM strictly enforced**: Views never directly access API or database
- **Stores are the single source of truth**: Views observe Stores via @Published
- **No business logic in Views**: Views only handle layout and user interaction
- **APIClient actor for all networking**: No raw URLSession calls in views or stores

### 14.2 SwiftUI Conventions
- Extract reusable views when used 2+ times (but not prematurely for single use)
- Use `Tokens.*` for ALL colors, fonts, spacing — never hardcode values
- Prefer `.task {}` over `.onAppear {}` for async work
- Use `@MainActor` on all Stores and ViewModels
- Avoid `AnyView` — use `@ViewBuilder` or concrete types

### 14.3 Review Checklist for AI-Generated iOS Code
1. Does it use `Tokens.*` for every visual value?
2. Does it follow the Store → View data flow? (no API calls in views)
3. Are animations functional, not decorative?
4. Does it handle loading/error/empty states?
5. Does it work in both light mode and dark mode? (currently light-only, but structure should allow future dark mode)
6. Is the Chinese/English text layout correct? (system font handles both, but check truncation)
