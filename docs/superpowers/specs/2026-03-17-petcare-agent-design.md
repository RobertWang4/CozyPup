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
User Input (text only, voice-to-text at OS level)
    │
    ▼
┌──────────────────────────────────────────────┐
│  FastAPI Backend                             │
│                                              │
│  ┌──────────────────────┐                    │
│  │ Emergency Keyword    │                    │
│  │ Detection (hardcode) │                    │
│  └──────────┬───────────┘                    │
│             │ (non-blocking prompt)           │
│             ▼                                │
│  ┌──────────────────────┐                    │
│  │ LLM Router           │                    │
│  │ (cheap model)        │                    │
│  │ → intent + entities  │                    │
│  └──────────┬───────────┘                    │
│             │                                │
│   ┌────┬───┴────┬────────┬────────┐          │
│   ▼    ▼        ▼        ▼        ▼         │
│  Chat Record  Summary   Map     Email       │
│  Agent Agent   Agent   Agent    Agent       │
│(strong)(cheap) (cheap)(cheap+API)(cheap)    │
│                                              │
│  ┌────────────────┐  ┌──────────────┐       │
│  │  PostgreSQL    │  │ Push Service │       │
│  │                │  │ (APNs)      │       │
│  └────────────────┘  └──────────────┘       │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  LiteLLM (Model Abstraction Layer)    │  │
│  │  - Unified API for all LLM providers  │  │
│  │  - Per-region model config            │  │
│  │  - Overseas: DeepSeek + Qwen Turbo    │  │
│  │  - Swappable to GPT/Claude/etc        │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  Map Abstraction Layer                │  │
│  │  - Overseas: Google Places API        │  │
│  │  - China: Amap (reserved)             │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

### 3.1 AI Framework

- **LiteLLM** for model abstraction — unified API across 100+ LLM providers, model switching is a config change
- **Hand-written agents** — each agent is a Python module with its own prompt template, no heavy framework (no LangChain)
- **FastAPI** handles HTTP, streaming (SSE), and orchestration

```python
# Pseudocode
import litellm

STRONG_MODEL = "deepseek/deepseek-chat"
CHEAP_MODEL  = "qwen/qwen-turbo"

def route(message, context):
    resp = litellm.completion(model=CHEAP_MODEL, messages=[...])
    return parse_intent(resp)

def chat_agent(message, context):
    return litellm.completion(model=STRONG_MODEL, messages=[...], stream=True)
```

### 3.2 Model Configuration

| Role | Overseas Default | China Default (future) |
|------|-----------------|----------------------|
| Strong model (Chat Agent) | DeepSeek-V3 | DeepSeek-V3 |
| Cheap model (Router, Record, Summary, Map, Email) | Qwen Turbo | Qwen Turbo |

### 3.3 Map Abstraction Layer

| Market | Provider | Cost |
|--------|----------|------|
| Overseas | Google Places API + cache | ~$150/mo per 1K users |
| China (future) | Amap (高德) | ¥50,000/yr base |

Cache strategy: same-area results cached for a few hours to reduce API calls.

## 4. Agent Design

### 4.1 LLM Router (cheap model)

Input: user message + recent chat context (last 10 messages or 2000 tokens, whichever is smaller)
Output:
```json
{
  "intent": "chat" | "record" | "summarize" | "map" | "email",
  "entities": {
    "pet_name": "optional",
    "keywords": []
  }
}
```

If LLM Router fails (timeout/error), fallback to `chat` intent.

### 4.2 Chat Agent (strong model)

- General conversation, health consultation, daily chat
- Rules: no diagnosis, no prescriptions, reference only
- Every consultation reply ends with disclaimer
- Has access to pet profiles and recent logs for context
- **Streaming response via SSE** — tokens sent to frontend as they are generated

### 4.3 Record Agent (cheap model)

Triggered when user explicitly says "record this" / "note this down" or provides appointment info.

Extracts structured data from current message:
```json
{
  "pet_name": "Doudu",
  "date": "2026-03-17",
  "category": "abnormal-vomiting",
  "summary": "Vomited yellow bile in the morning",
  "reminder": null
}
```

Writes to pet_logs + calendar_events. Checks for existing entries on the same date with similar content to avoid duplicates.

### 4.4 Summary Agent (cheap model)

Triggered when user says "summarize today's chat to calendar" or similar.

- Reviews current conversation session (bounded by session_id)
- Extracts key health events and decisions
- Checks existing pet_logs to avoid duplicate entries
- Writes summarized entries to pet_logs + calendar_events
- Flags items needing push notifications → writes to reminders table

### 4.5 Email Agent (cheap model)

Triggered when user says "help me write an appointment email" or "generate an email for the vet" or similar.

- Gathers context from recent conversation (symptoms, timeline, pet profile)
- Generates a professional appointment/consultation email in the user's language
- Includes: pet info, symptom summary with dates, questions for the vet
- User reviews in chat, can ask for edits, then copies or shares

Example output:
```
Subject: Appointment Request - [Pet Name] - [Symptom Summary]

Dear Dr. [___],

I am writing to request an appointment for my [species/breed], [name] ([age]).

Over the past [timeframe], [name] has experienced the following:
- [date]: [symptom/event]
- [date]: [symptom/event]

I would appreciate your earliest available appointment. Please let me know
what additional information you may need.

Thank you,
[Owner Name]
```

### 4.6 Map Agent (cheap model + Google Places API)

- Understands user intent ("weekend outdoor with dog" → parks, not pet stores)
- Calls Google Places API with appropriate query
- Organizes and recommends results with context

### 4.7 Multi-Pet Resolution

All agents must identify which pet the user is talking about:
1. Explicit name match ("Doudu is sick" → Doudu)
2. Context inference (if user only has one pet, default to it)
3. If a single message mentions multiple pets, agents create separate entries per pet
4. Ambiguous → agent asks "Which pet are you referring to?"

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

A new session is created when: (a) user opens the app with no active session, or (b) 30+ minutes of inactivity.

### chats
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| session_id | UUID | FK → chat_sessions |
| user_id | UUID | FK → users |
| role | VARCHAR | user / assistant |
| content | TEXT | Message content |
| intent | VARCHAR | Router-identified intent (nullable, only for user messages) |
| pet_ids | UUID[] | Array of resolved pet IDs (nullable) |
| created_at | TIMESTAMP | |

### pet_logs
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| pet_id | UUID | FK → pets |
| log_date | DATE | Date |
| category | VARCHAR | diet / excretion / abnormal / vaccine / deworming / medical / daily |
| summary | TEXT | AI summary |
| raw_text | TEXT | Original input or conversation excerpt |
| source | VARCHAR | direct / conversation |
| edited | BOOLEAN | Whether manually edited by user |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

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
| log_id | UUID | FK → pet_logs (optional) |
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

### Health Logs
```
GET    /api/v1/pets/:id/logs    Get pet's health logs
PUT    /api/v1/logs/:id         Edit log entry
DELETE /api/v1/logs/:id         Delete log entry
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
- React + Capacitor (iOS packaging)
- Single-page chat-centric UI

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
- **Voice input:** Uses iOS system keyboard voice input, converted to text immediately

### Chat UI Elements
- Standard chat bubbles for user/assistant (streamed via SSE)
- Structured cards embedded in AI replies (health record confirmation, map recommendations, email drafts)
- Emergency prompt banner (non-blocking, dismissible)

### Location Handling
- Location permission requested on-demand (first time Map Agent is triggered)
- Frontend sends GPS coordinates with the chat message when map intent is likely
- Fallback: if no location available, Map Agent asks user to share location or enter an address

## 8. Emergency Prompt (Non-Blocking)

**Not an intercept — a suggestion.**

1. Hardcoded keyword detection runs before Router (seizure, poison, choking, bleeding, difficulty breathing, collapse, etc.)
2. If triggered: AI responds normally + a dismissible banner appears:
   > "Detected a possible emergency. Want to find a nearby 24-hour pet ER?"
3. User taps "Find" → Map Agent searches for emergency vet clinics
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

Per 1,000 monthly active users, 5 interactions/day:

| Component | Monthly Cost |
|-----------|-------------|
| DeepSeek-V3 (Chat Agent) | ~$50 |
| Qwen Turbo (Router + Record + Summary + Map + Email) | ~$10 |
| Google Places API (with cache) | ~$160 |
| PostgreSQL (cloud) | ~$20 |
| APNs push | $0 |
| **Total** | **~$240/month** |

Model abstraction layer (LiteLLM) allows swapping to cheaper or better models as the market evolves.

## 11. Out of Scope for MVP

- Voice conversation (voice is input-only via OS keyboard)
- RAG / vector search
- Social features
- Amap integration (reserved in abstraction layer)
- Pet health report generation
- Multi-language (English first, Chinese later)
- Data export
