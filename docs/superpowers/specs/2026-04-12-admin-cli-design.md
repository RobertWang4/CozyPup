# Admin CLI Design

**Date:** 2026-04-12
**Status:** Design
**Author:** Robert + Claude
**Scope:** Phase 0 (foundation) + Phase 1 (observability) + Phase 2 (user/subscription) + Phase 3 (ops / kill switches). Phase 4 (content ops, metrics) is out of scope for this spec and will get a separate one.

## 1. Motivation

CozyPup today ships a read-only `debug` CLI (`backend/app/debug/cli.py`) that talks to Cloud Logging and the local DB to inspect traces, errors, and token usage. It has three gaps:

1. **Error triage is multi-step.** When a user reports "the app broke", Robert has to chain `debug lookup → debug requests → debug trace → psql` to reconstruct what happened. The original user message, pet context, and session history are scattered.
2. **There is no write path.** Subscription extensions (refunds, customer support), bans, data fixes, and feature kills all require hand-written SQL or a redeploy. This is both slow and unsafe.
3. **There is no audit trail.** Any write to prod today is untraceable.

We want a single `admin` CLI that is the canonical entrypoint for all operational work on CozyPup — observability, user/subscription management, and ops emergencies — with proper authentication, auditing, and safety rails suitable for a production SaaS product.

## 2. Goals & Non-Goals

### Goals

- One tool (`admin`) for all operator workflows, with a discoverable command tree.
- **One command** to see everything relevant about a user, including their last error with full context (message, images, pets, session).
- Safe writes to production: authenticated, audited, dry-runnable, reversible where possible.
- Full backward compatibility with existing `debug` commands during migration.
- Output that is equally usable by humans (pretty tables) and scripts/AI (`--json`).
- Final deliverable: `docs/ADMIN_CLI.md` usage manual, linked from `CLAUDE.md`.

### Non-Goals

- Web dashboard. Architecture keeps this possible later but does not build it.
- Multi-tenant admin (one org, one user base, one admin team).
- Full RBAC. We have one admin scope; no fine-grained per-command permissions.
- Content operations (RAG ingest, push broadcast) and business metrics dashboards — deferred to Phase 4.
- Replacing Cloud Logging / gcloud for log storage. We read from it, we don't replace it.

## 3. High-Level Architecture

```
┌─────────────────────────┐        HTTPS + admin JWT       ┌──────────────────────────────┐
│  Local CLI (admin)      │ ─────────────────────────────▶ │  Cloud Run: backend          │
│  backend/app/admin_cli/ │                                │                              │
│                         │ ◀──────── JSON / NDJSON ─────  │  /api/v1/admin/*             │
│  ~/.cozypup/admin.json  │                                │  require_admin dependency    │
│  (JWT + prefs)          │                                │  admin_audit_log (DB table)  │
└─────────────────────────┘                                └──────────────┬───────────────┘
           │                                                              │
           │ read-only, for log queries                                   ▼
           └──────────▶  gcloud logging read ─────────▶ Cloud Logging (trace entries)
                                                                          │
                                                              Neon Postgres (shared)
```

Four components:

1. **`backend/app/admin_cli/`** — new Python package, click-based. Replaces `backend/app/debug/cli.py` as the shipping CLI. Old debug commands live on as `admin debug *` subcommands.
2. **`backend/app/routers/admin/`** — new FastAPI routers under `/api/v1/admin`, one file per domain. All routes depend on `require_admin`.
3. **`admin_audit_log` table** — every write operation leaves a row here inside the same transaction as the business change.
4. **`~/.cozypup/admin.json`** — local CLI state: current admin JWT, default `--env`, recently used user IDs.

### Trust boundary

- **Reads** may go either through the admin API (for anything that requires DB access at scale or complex joins) or directly via `gcloud logging read` (for log-heavy observability commands). The gcloud path inherits the operator's gcloud auth, so no additional admin JWT is needed for log reads.
- **Writes** must go through the admin API. The CLI never touches the DB directly for writes. This keeps business validation and audit in one place.

## 4. Phase 0 — Foundation

Phase 0 builds the primitives every later phase depends on.

### 4.1 Admin identity

Extend the existing `User` model:

```python
class User(Base):
    ...
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
```

Admin-ness is a flag on a normal user account. Robert logs in with his own Google/Apple account; a DB migration flips `is_admin=true` for his user id. No separate admin users table.

### 4.2 Admin JWT scope

Today's JWTs are app-facing and long-lived. We add a second, short-lived scope:

- **`scope: "user"`** — what iOS clients get today. Cannot call `/api/v1/admin/*`.
- **`scope: "admin"`** — issued only by `POST /api/v1/admin/auth/login`. TTL 2 hours. Required for every admin route.

`create_access_token()` in `auth.py` gains a `scope` argument (default `"user"` for backward compatibility). `verify_token()` returns the scope, and the new `require_admin` dependency rejects anything that isn't `scope=="admin" and user.is_admin`.

Rejection returns **404** (not 403) when the caller is unauthenticated or lacks admin, to avoid advertising the admin surface. Authenticated admins with expired tokens get a proper 401 so the CLI can re-login.

### 4.3 Admin login flow

```
admin login
  ↓
CLI opens browser → http://localhost:<random>/callback (local loopback)
  ↓
Browser redirects to backend OAuth start → Google/Apple OAuth →
  backend callback with new query param ?admin=1
  ↓
Backend verifies OAuth, loads User, checks user.is_admin=true,
  issues admin-scoped JWT (TTL 2h), redirects to CLI loopback with token
  ↓
CLI saves token + expiry to ~/.cozypup/admin.json (mode 0600)
```

**Dev shortcut**: `admin login --dev` calls `POST /api/v1/admin/auth/dev-login` with a body `{"email": "robert@x.com"}`. This endpoint is gated by `settings.environment == "dev"` so it is not reachable in prod. It skips OAuth entirely and is the fast path for local testing.

Additional auth commands:

- `admin logout` — deletes the local token file.
- `admin whoami` — prints `email, scope, expires_in`.
- `admin config set default_env dev` — persists preferences to `~/.cozypup/admin.json`.

### 4.4 Audit log

New table:

```python
class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    admin_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)          # e.g. "sub.extend"
    target_type: Mapped[str | None] = mapped_column(String(32))              # "user" | "subscription" | ...
    target_id: Mapped[str | None] = mapped_column(String(128))               # the affected resource id
    args_json: Mapped[dict] = mapped_column(JSONB, nullable=False)           # sanitized args + reason
    result_json: Mapped[dict] = mapped_column(JSONB, nullable=False)         # before/after diff
    ip: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_audit_admin_created", "admin_user_id", "created_at"),
        Index("ix_audit_target", "target_type", "target_id"),
        Index("ix_audit_action_created", "action", "created_at"),
    )
```

Writes are enforced via a decorator on admin route handlers:

```python
@router.post("/users/{user_id}/ban")
@audit_write(action="user.ban", target_type="user")
async def ban_user(user_id: UUID, body: BanRequest, ctx: AdminContext = Depends(require_admin)):
    ...
```

The decorator:

1. Captures request body (minus secrets) as `args_json`.
2. Requires `body.reason` to be non-empty; rejects with 422 otherwise.
3. Runs the handler.
4. Writes the audit row **in the same transaction** as the business change. If the business change fails, the audit row is rolled back too — the audit log reflects only completed changes.
5. Returns the result envelope with the generated `audit_id` so the CLI can show it.

**Retention:** permanent by default. `admin audit prune --before 90d --yes` exists for manual cleanup; it is never triggered automatically.

### 4.5 CLI conventions

Every command obeys the same global flags:

| Flag | Meaning |
|---|---|
| `--env prod\|dev` | Which backend to target. Default from `~/.cozypup/admin.json` (prod). |
| `--json` | Emit machine-readable JSON instead of human tables. |
| `--dry-run` | For writes: compute the diff and show it, do not persist. Default **on** for destructive writes (delete, revoke, ban). |
| `--yes` | Skip the "are you sure" prompt. For destructive writes, even `--yes` still requires the reason flag. |
| `--reason "text"` | Mandatory for all writes. Stored in `args_json.reason`. |

**Destructive write confirmation pattern:** for `user delete`, `user ban`, `sub revoke`, the CLI prints the proposed diff and asks the operator to type the target's primary identifier (email for users) before proceeding. `--yes` skips the typed confirmation but not the reason requirement.

**Output**: human output is click-rendered Unicode tables with color. `--json` outputs a single top-level envelope `{"data": ..., "audit_id": "...", "env": "prod"}` so jq pipelines stay uniform.

### 4.6 Remote connection

The CLI is always a thin HTTP client against one of two base URLs:

- `prod` → `https://backend-601329501885.northamerica-northeast1.run.app`
- `dev` → `http://localhost:8000`

No direct Neon connection from the CLI. All DB-backed commands go through the backend. Log reads go through `gcloud logging read` (inherits the caller's gcloud auth).

### 4.7 Migration of existing debug commands

All current `debug` commands (`lookup`, `trace`, `requests`, `tokens`, `errors`, `modules`, `summary`, `user`, `users`, `replay`, `generate-test`) are rehomed under `admin debug *` with identical flags and output. We also ship a `debug` shim entry point that forwards to `admin debug` and prints a one-line deprecation notice the first time per day. This gives a soft landing for muscle memory and any scripts.

## 5. Phase 1 — Observability 2.0

Phase 1 is the heart of this spec. Its **central promise**:

> One command gets everything about a user — profile, subscription, pets, full chat history, and every error they've hit — and from any chat message I can drill into the complete pipeline that produced it: what they typed, what images they sent, what prompt the LLM received, what the LLM replied, which tools were called with which arguments, what each tool returned, and how the next round of the loop produced the final output.

Two commands deliver this. `admin user inspect` is the top-down aggregate view; `admin trace` is the bottom-up pipeline view. Every row in `inspect` carries a `correlation_id` so you can drill into `trace` without copy-pasting identifiers.

### 5.1 `admin user inspect <id|email>`

The flagship observability command. It produces an aggregated report drawn from three sources (DB, Cloud Logging, audit log) in a single page:

```
═══════════════════════════════════════════════════════════════
  USER  robert@x.com  (id: 8f3c...)
═══════════════════════════════════════════════════════════════
  Created        2026-02-14  (57 days ago)
  Auth           google
  Subscription   active · Pro · expires 2026-05-01 (19 days)
  Pets           2 — 豆豆 (柴犬, 3y), Luna (英短, 5y)
  Flags          is_admin=false  banned=false

  Last 24h       14 messages · 1 error · 42k tokens · $0.08
  Session today  cs_20260412_…  (opened 09:14, 8 msgs)

──  Recent activity (last 20 events) ──────────────────────────
  09:14  ✓ chat       "豆豆今天不吃东西…"
  09:15  ✓ tool       log_event(category=health)
  09:16  ✓ chat       "要不要带去医院?"
  10:02  ✗ chat       "[image] 这个伤口严重吗"    ← ERROR
         └─ correlation: 7a2f...
         └─ module: app.agents.orchestrator
         └─ KeyError: 'tool_result'
  10:33  ✓ chat       "好的谢谢"

  Next actions:
    admin trace 7a2f              # full pipeline replay
    admin user export 8f3c...     # GDPR data bundle
    admin sub show 8f3c...        # subscription detail
```

Implementation sketch:

- DB read: `users`, `pets`, `chat_sessions`, `chats` (the message table — joined for full chat history), latest aggregates (token usage last 7d/24h).
- Cloud Logging read: `chat_request` + `error_snapshot` entries for this user, last N hours, bucketed by time. We already persist `user_id` on every trace entry, so this is a gcloud filter query.
- Audit log read: any admin actions against this user.
- All four merged in memory into the activity timeline. **Each row is annotated with its `correlation_id`** (from the `chats.correlation_id` column we start persisting in this phase — see §5.3), so drilling into any message with `admin trace <cid>` is always one step away.

Flags:

- `--since 24h|7d|30d|all` (default 24h). `all` shows the full chat history since account creation.
- `--chats all` — swap the default 20-event "recent activity" block for the **complete chat history** of the user. Pairs with `--since all` for a full archive view.
- `--chats errors` — show only the user's messages that resulted in an error (on screen and in the pipeline). Fastest path from "the user is unhappy" to "here's what broke."
- `--last-error` — skip the aggregate view entirely and jump straight to `admin trace` for the most recent error this user encountered. Equivalent to running `admin user inspect --chats errors` and piping the top `correlation_id` into `admin trace`.
- `--session <id>` — scope the activity block to a single chat session.
- `--json` — emit a structured report instead of the table. Every entry in the JSON carries `correlation_id`, `session_id`, `timestamp`, `role`, `content`, and `error` (nullable object).

The JSON shape of the activity list is deliberately designed so that an AI assistant piping `admin user inspect --json | jq` can iterate messages and call `admin trace` for each error without any string parsing.

### 5.2 `admin trace <correlation_id>`

The complete pipeline view for a single chat turn. Given any `correlation_id` — whether pulled from an error report, from `admin user inspect`, or from a user's bug screenshot — this command reconstructs the **entire path** from the user's input to the final output that was streamed back to their device.

**The full pipeline shown, in order, for every trace:**

1. **User input** — the raw user message, the raw image URLs (with clickable/openable thumbnails), the session id, the chat session's recent history tail (previous 4 turns), and the client version if known.
2. **Pre-processing** — language detection, emergency keyword match result, pre-processed tool suggestions, and the pet snapshot (each pet's species/breed/age/weight/chronic conditions at request time — pulled from the stored snapshot, not live DB, so historical traces are accurate).
3. **LLM request (round 1)** — the full message array sent to the LLM: system prompt, history, current user turn. The available tool catalog (count + name list by default, `--show-tools` to print the full JSON schemas). Model name, temperature, streaming flag.
4. **LLM response (round 1)** — the content the LLM produced, token counts (prompt / completion / total), and the list of `tool_calls` it requested with their full JSON arguments.
5. **Tool execution** — for each tool call: the tool name, the validated arguments, the handler module path, the full return value (card JSON included), and any side effects recorded (DB writes, cards emitted to iOS).
6. **LLM request (round 2+)** — subsequent rounds if the orchestrator went back to the LLM with tool results. Each round's messages, response, and tool calls are printed in order, indented under the round header, so a multi-step plan execution is visually a tree.
7. **Final output** — the `chat_response` event: the text that was streamed to the user, the cards emitted, any emergency escalation, and the assistant message id that got persisted to `chats`.
8. **Error overlay** — if any step raised, the stack trace is inlined **at the step where it happened**, not appended at the bottom. Everything before the error is still shown so you can see the context that led to it.

Additional visual/UX features on top of today's `debug trace`:

- **Per-step timing** relative to request start (e.g. `+2140ms`).
- **Round grouping**: each LLM round and its associated tool calls are boxed together so it's obvious which tool results fed which follow-up LLM call.
- **Image handling**: `--open-images` opens attached image URLs in the default browser. Thumbnails inline in iTerm2 when supported.
- **Next-action footer**: suggested follow-up commands (`admin replay`, `admin trace --raw`, `admin trace --llm-full`).

Flags:

- `--raw` — dump the raw JSON trace entries in the order they were logged, no pretty rendering. For machine consumption and for when the pretty view is hiding something.
- `--show-tools` — include the full JSON schemas of the available tools in the round 1 section (off by default because it's verbose).
- `--show-system-prompt` — include the full system prompt text (off by default; it's long and usually stable).
- `--replay` — reconstruct the request payload and re-POST it to the backend with an `X-Admin-Replay: true` header. The replay is tagged with a new correlation id and writes a `trace_replay_of:<original>` audit row. Requires `--reason`.
- `--llm-full` — when the debug collector captured a parallel non-streaming LLM call, print its full response including any content that was streamed in chunks.
- `--json` — same content as the pretty view, but as a structured document with one object per pipeline step.

### 5.3 Capturing richer trace context

To make "drill from any chat message to its full pipeline" work reliably, we need two things: the DB row for a message must know its trace, and the trace itself must carry enough context to be self-contained.

**Persist `correlation_id` on the `chats` table.** Add a nullable `correlation_id` column on the `chats` model. When the chat router writes the user turn and the assistant turn to the DB, it stores the current request's correlation id. This is the join key that powers `admin user inspect` → `admin trace`: every message in the activity list has its `correlation_id` already embedded, and the operator can pipe it into `admin trace` with no guesswork.

**Extend the `chat_request` trace payload.** Current `chat_request` trace only logs `message`, `image_urls[:100]`, `session_id`. We extend it to also persist:

- `pet_snapshot`: compact JSON of the pets at request time (`[{id, name, species, breed, age_months, weight_kg, chronic_conditions}]`). This lets future trace views show pet context without re-querying live DB (which may have changed).
- `session_history_tail`: last 4 `{role, content_preview}` pairs from the session, truncated at 200 chars each.
- `client_version`: pulled from `User-Agent` or a new `X-Client-Version` header the iOS app starts sending.
- `image_urls_full`: the full image URLs (not the `[:100]` truncation), so `--open-images` can actually open them. Storage cost is bounded because the chat_request event is once per request.

These fields are added to the existing `trace_log("chat_request", ...)` payload in `backend/app/routers/chat.py`. Size is bounded (few KB), and goes into the same Cloud Logging sink.

**Extend `llm_response` trace payload.** Today it logs `model`, `prompt_tokens`, `completion_tokens`, `tool_calls`. We also persist the full `content` text (the model's non-tool-call output for the round). Without this, `admin trace` cannot show "what the LLM actually said in round 1" for non-streaming rounds, which is a gap.

**Extend `tool_result` trace payload.** Today it logs tool name and a success flag. We add `result` (the full return value, including the emitted card JSON) so `admin trace` can show what each tool actually returned without replaying.

For `error_snapshot`: we already persist request body. We additionally attach `correlation_id` (already present) and `user_id` (already present) so `admin user inspect` can join by user.

**Size guardrails.** Each trace entry is capped at 64 KB after JSON serialization; if an image URL list or a tool result would exceed that, the overflow is truncated and a `_truncated: true` marker is added. Cloud Logging's own entry size limit is 256 KB, so we stay well under it.

### 5.4 The end-to-end drill-down workflow

This is the single most important workflow in the CLI and it deserves an explicit walk-through.

```
# Robert receives a support ticket: "Robert, the app broke when I sent a photo
# of my dog's wound this morning." User email: alice@example.com

$ admin user inspect alice@example.com --chats errors
  → shows Alice's profile + the 3 messages that led to errors in the last 24h
  → the most recent one is 10:02  "[image] 这个伤口严重吗"  correlation 7a2f...

$ admin trace 7a2f
  → full pipeline:
      [01] user sent "这个伤口严重吗" + 1 image (thumbnails shown)
      [02] pet snapshot: 豆豆 (dog, 柴犬, 3y), Luna (cat, 英短, 5y, CKD stage 2)
      [03] session tail: last 4 turns (they had been discussing 豆豆's appetite)
      [04] language=zh, emergency=false
      [05] LLM round 1: grok-4-1-fast, 8 messages, 1 image
              content:    "从图片看伤口有渗出..."
              tool_calls: log_event(category=health, pet_id=豆豆, ...)
              tokens:     1823 in / 412 out
      [06] tool log_event → ok, card emitted
      [07] LLM round 2: BLOW UP — KeyError: 'tool_result'
              app/agents/orchestrator.py:287
              (full stack)

# Robert now knows:
#   - The exact message
#   - The exact image
#   - The exact tool call and its result
#   - The exact place in the orchestrator that failed
#   - The exact pet context at that moment

# Fix, replay to verify, done:
$ admin trace 7a2f --replay --reason "verify orchestrator fix"
```

This is the **one-command promise**: from a user complaint with nothing but an email, you are two commands away from every byte of context needed to understand what happened.

### 5.5 `admin errors recent`

Dashboard-style command for proactive error discovery:

```
admin errors recent --since 24h
admin errors recent --since 7d --module app.agents.orchestrator
admin errors recent --since 24h --user 8f3c
admin errors recent --since 24h --group-by user
```

Groups errors by (module, error_type) or (user) and shows counts, sample correlation ids, and "most recent" timestamps. Built on the existing error snapshot loader plus Cloud Logging search.

### 5.6 `admin user export <id>`

GDPR-friendly bundle. Zips:

- All `users`, `pets`, `chat_sessions`, `chats`, `calendar_events`, `reminders` rows for the user
- The last 30 days of trace entries for that user from Cloud Logging
- Audit log entries targeting that user

Writes to a local `./export-<user_id>-<timestamp>.zip`. Mandatory `--reason`. Audited. Fields containing bcrypt hashes or refresh tokens are redacted.

### 5.7 `admin user impersonate <id>`

Issues a short-lived `scope=user` JWT for the target user. Used to reproduce a bug from the user's perspective (curl the chat endpoint, or paste the token into an iOS simulator build):

- TTL capped at 15 minutes, default 10 minutes.
- Token is printed only to the terminal, never logged.
- Audited as `user.impersonate` with the reason.
- Target user sees no change (no session cookie, no revocation of their active sessions).

This lives in Phase 1 because its primary use case is debugging. Phase 2 reuses the same endpoint.

## 6. Phase 2 — User & Subscription Management

### 6.1 Subscription commands

Backed by the existing `users.subscription_status|_expires_at|_product_id` columns. `backend/app/routers/admin/subscriptions.py` exposes:

```
POST /api/v1/admin/subscriptions/{user_id}/grant    # set status=active, product, expiry
POST /api/v1/admin/subscriptions/{user_id}/extend   # expires_at += delta
POST /api/v1/admin/subscriptions/{user_id}/revoke   # set status=expired, expiry=now
POST /api/v1/admin/subscriptions/{user_id}/verify   # re-check via StoreKit receipt
GET  /api/v1/admin/subscriptions/{user_id}          # show current state + recent audit rows
GET  /api/v1/admin/subscriptions                    # list + filter
```

CLI:

```
admin sub show <user>
admin sub grant <user> --tier pro --until 2026-12-31 --reason "beta tester"
admin sub extend <user> --days 30 --reason "customer support refund"
admin sub revoke <user> --reason "chargeback"
admin sub verify <user>
admin sub list --status expired --expired-within 7d
```

`verify` hits StoreKit's verification endpoint (the same code path the iOS client uses) and diffs the result against the DB. If they disagree, the command prints the diff and exits non-zero without writing; the operator explicitly chooses to reconcile with `--reconcile`.

All writes go through `@audit_write`. `extend` and `grant` default to dry-run off (they're additive, low risk) but still require `--reason`. `revoke` defaults to dry-run on and requires typed email confirmation.

**Duo plan handling:** if the user is a Duo member (`product_id` ends with `.duo`), mutating their subscription prints a warning and requires `--force-duo`, because these changes usually should be made on the payer. `admin sub show` includes the duo relationship in its output.

### 6.2 User management commands

```
admin user search "张"                    # partial match on name/email
admin user inspect <id|email>             # (Phase 1)
admin user ban <id> --days 7 --reason "spam"
admin user unban <id> --reason "appeal granted"
admin user delete <id> --reason "user request"
admin user export <id>                    # (Phase 1)
admin user impersonate <id> --ttl 10m     # (Phase 1)
```

**Ban** sets a new `users.banned_until` column (nullable timestamp). The existing auth middleware learns to return 403 when `banned_until > now()`. Unban sets it to `NULL`.

**Delete** is soft: set `users.deleted_at = now()` and null out PII fields (email, name, avatar_url) immediately. Hard delete happens via a separate scheduled job after 30 days (not part of this spec). `admin user delete` refuses if the user has an active paid subscription — operator must revoke first.

### 6.3 Data access patterns

For user commands, the target can be specified as an email, a UUID, or a prefix of a UUID (like today's `debug` CLI). Resolution happens server-side in `require_admin`-protected helpers that also double-check ownership/existence with proper errors.

## 7. Phase 3 — Ops & Kill Switches

### 7.1 Rate limit clearing

Today `ChatRateLimit` middleware caps 30 messages/hour per user. Storage is an in-memory dict keyed by user id. Phase 3 adds:

```
POST /api/v1/admin/ops/ratelimit/clear     { "user_id": "..." }   # one user
POST /api/v1/admin/ops/ratelimit/clear     { "all": true }         # everyone
```

`admin ops ratelimit clear --user 8f3c --reason "…"`

The middleware exposes a module-level `clear(user_id | None)` function; the admin route calls it directly. Audited.

### 7.2 Session revocation

Today JWTs are stateless and live until expiry. For "force logout", we introduce a lightweight `token_revocation` table keyed by `user_id` and `revoked_at`. `verify_token()` rejects tokens whose `iat < revoked_at` for that user.

```
admin ops session revoke <user> --reason "suspected stolen device"
```

This invalidates all of the user's outstanding JWTs immediately. Their iOS app will get 401 on the next request and transition to the login screen.

### 7.3 Feature flags

New table:

```python
class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

Runtime: a module `backend/app/flags.py` exposes `get_flag(key, default)` and maintains an in-process cache refreshed every 30 seconds via background task. Backend code that wants to consult a flag calls `get_flag("emergency_routing", default=True)`.

Initial flag inventory (the ones that unblock real scenarios):

- `auth_dev_enabled` (bool, default `true` in dev / `false` in prod) — gates the `POST /api/v1/auth/dev` endpoint. This directly addresses the CLAUDE.md TODO item about killing `/auth/dev` in prod.
- `emergency_routing` (bool, default `true`) — toggles Kimi routing for emergency keywords. Setting to `false` forces all chat through grok-4-1-fast.
- `broadcast_banner` (object, nullable) — `{"text": "…", "severity": "info|warn|error"}`. iOS app fetches this via a new public `GET /api/v1/flags/public` endpoint (read-only subset) and shows a top banner.
- `chat_rate_limit_per_hour` (int, default 30) — override the ChatRateLimit constant without a redeploy.

CLI:

```
admin ops flags list
admin ops flags get <key>
admin ops flags set <key> <value>      # value parsed as JSON
admin ops flags unset <key>            # deletes the row
```

Every mutation is audited and the cache refresh is triggered immediately (not just on the 30s tick) by a pg_notify call so the change is visible in <1 second on all backend instances.

### 7.4 Cache flush

`admin ops cache flush --key pets:<user>` — no-op placeholder for now, because CozyPup doesn't yet have a named cache layer. The command and route exist so the shape is established; the implementation is a stub that logs the request and returns ok. When we add Redis later, this command already works.

## 8. Audit Log Querying

```
admin audit list --since 24h
admin audit list --admin robert@x.com --since 7d
admin audit list --target-user 8f3c
admin audit list --action sub.extend --since 30d
admin audit show <audit_id>                        # full diff
admin audit prune --before 90d                     # manual retention (destructive, typed confirm)
```

This matters because the audit log is the primary answer to "who changed X?" and the primary evidence for ourselves during post-incident review.

## 9. Security Considerations

1. **Admin JWT is short-lived (2h) and scope-restricted.** App JWTs cannot hit admin routes even if the caller's `is_admin=true`; the token must be issued via `admin login`.
2. **Admin endpoints return 404 to unauthenticated callers**, not 403. The admin surface is not advertised.
3. **Destructive operations require three things**: `--reason`, typed confirmation, and explicit `--yes`. Defaults lean safe.
4. **All writes are audited in the same transaction** as the business change. A successful business change always has its audit row; a failed one never does.
5. **The `dev-login` endpoint is gated on `settings.environment == "dev"`.** It does not exist in prod. This is checked by looking at the actual Cloud Run env var.
6. **The local token file (`~/.cozypup/admin.json`) is 0600 and stored under the user's home directory**, not in the repo. CLI refuses to run if the file is group/world readable.
7. **Impersonation tokens are `scope=user` and capped at 15 minutes**. They can be used to reproduce user-side bugs but cannot hit admin routes.
8. **gcloud-backed commands inherit the operator's gcloud auth**. Operators without `logging.viewer` on the project get a clear error from the CLI.

## 10. Testing Strategy

- **Unit tests** for `require_admin`, `audit_write` decorator, JWT scope verification. These are the security-critical primitives.
- **Integration tests** (`pytest` + test client) for each admin write endpoint, verifying both the business effect and the audit row.
- **CLI smoke tests**: a thin test matrix that invokes the CLI against a local dev backend and asserts on `--json` output shape. Not end-to-end with Cloud Run; we trust integration tests for that.
- **Regression suite**: after migration, re-run existing `debug` command invocations via the new `admin debug` path and diff the output. This is the safety net for the rehoming.

## 11. Rollout Plan

Phase 0 ships in full before any other phase (it's infrastructure). Then Phases 1, 2, 3 ship in that order, each gated on its own user acceptance test against a real workflow:

1. **Phase 0 done** when `admin login`, `admin whoami`, a dummy `POST /api/v1/admin/ping` route (authed + audited), and the audit table migration are live in prod.
2. **Phase 1 done** when Robert can say "a user reported X broke at 10:02" and run a single `admin user inspect <email>` that surfaces the broken request with its pet context, session tail, and stack trace.
3. **Phase 2 done** when Robert can process a subscription refund and user ban end-to-end without SQL.
4. **Phase 3 done** when `auth_dev_enabled` flag actually gates the dev auth endpoint and Robert can flip it from the CLI.

Each phase ends with an update to `docs/ADMIN_CLI.md` covering the new commands, and a commit that adds a cheat-sheet entry to `CLAUDE.md` so future Claude sessions load the reference automatically.

## 12. Documentation Deliverable

At the end of Phase 3, we ship `docs/ADMIN_CLI.md`. It is the canonical operator manual, designed for two readers:

**Human readers** — Robert looking up a command at 11pm while handling a support ticket:

- Install and first-run
- Environment switching
- Global flags (`--env`, `--json`, `--dry-run`, `--yes`, `--reason`)
- Full command reference: one section per command group, each command with syntax, description, one worked example, and common errors
- Five scenario playbooks:
  1. "A user reported the app crashed after sending an image" — full triage walkthrough
  2. "A user asked for a refund for last month" — subscription extension
  3. "An account is spamming the chat endpoint" — rate-limit clear → ban
  4. "We need to kill `/auth/dev` right now" — feature flag emergency
  5. "Post-incident review: who changed what last Tuesday?" — audit log querying
- Troubleshooting: expired token, wrong env, gcloud auth missing, 404-on-admin-route pitfalls

**AI readers** — future Claude Code sessions that will help Robert operate CozyPup:

- A structured "AI Cheatsheet" section at the top, inside `<!-- ai-cheatsheet -->` HTML comments, that lists every command with a one-line purpose and the typical flags, so a session can find the right command without reading the whole manual.
- Common misuses and gotchas explicitly called out (e.g. "`admin sub extend` requires `--days`, not `--until`").
- A pointer from `CLAUDE.md` so the doc is loaded in every session by default.

## 13. Open Questions

None blocking. Implementation will likely surface edge cases around StoreKit receipt format and the exact shape of the feature flag refresh mechanism; we'll resolve those in the implementation plan, not here.

## 14. Directory Layout

```
backend/app/
├── admin_cli/
│   ├── __init__.py
│   ├── main.py              # click entrypoint, subcommand registration
│   ├── client.py            # HTTP client wrapper around ~/.cozypup/admin.json
│   ├── config.py            # token + prefs read/write (0600)
│   ├── output.py            # --json / --dry-run / table rendering helpers
│   ├── auth_cmd.py          # login / logout / whoami / config
│   ├── user_cmd.py          # search / inspect / export / impersonate / ban / delete
│   ├── sub_cmd.py           # show / list / grant / extend / revoke / verify
│   ├── ops_cmd.py           # ratelimit / flags / session / cache
│   ├── obs_cmd.py           # errors / trace / replay
│   ├── audit_cmd.py         # list / show / prune
│   └── debug_cmd.py         # rehoming of existing debug commands
├── routers/admin/
│   ├── __init__.py          # router = APIRouter(prefix="/api/v1/admin"); mounts subrouters
│   ├── deps.py              # require_admin, AdminContext, audit_write decorator
│   ├── auth.py              # admin login / dev-login / whoami
│   ├── users.py
│   ├── subscriptions.py
│   ├── ops.py
│   ├── observability.py
│   └── audit.py
├── flags.py                 # get_flag(), cache + refresh
└── models.py                # + User.is_admin, User.banned_until, User.deleted_at
                             # + AdminAuditLog, FeatureFlag, TokenRevocation

docs/
└── ADMIN_CLI.md             # (written at end of Phase 3)
```

## 15. What's Explicitly Deferred

- Content operations: `admin rag *`, `admin push *`
- Metrics: `admin metrics *`
- Multi-operator features: per-admin API keys, scoped roles, approvals
- Web dashboard
- Automated audit retention policies
- Hard delete job (the 30-day follow-up to soft delete)

These are real and we will address them, but not in this spec.
