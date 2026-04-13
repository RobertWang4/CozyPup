# CozyPup Admin CLI — Operator Manual

Thin HTTPS client for operating CozyPup in prod: inspect users, trace requests, replay errors, impersonate for bug reproduction, and export GDPR bundles — all from the terminal.

---

<!-- ai-cheatsheet -->

## AI Cheatsheet

| Command | Purpose | Typical flags |
|---------|---------|---------------|
| `admin login` | Obtain an admin JWT and store it at `~/.cozypup/admin.json` | `--dev --email robert@example.com` (local), `--env prod` (OAuth) |
| `admin logout` | Delete the stored admin JWT | — |
| `admin whoami` | Print current admin identity + token expiry | `--json` |
| `admin config show` | Print all stored config values | `--json` |
| `admin config set` | Persist a single config key | `admin config set base_url https://...` |
| `admin ping` | Verify the backend is reachable and admin scope works | `--reason "checking prod health"` |
| `admin user inspect <target>` | Full user snapshot: profile, pets, recent chats, error summary | `--chats 20 --errors --json` |
| `admin user export <target>` | Generate a GDPR-compliant data bundle (zip) for a user | `--reason "GDPR request #42" --out /tmp/export.zip` |
| `admin user impersonate <target>` | Mint a short-lived user JWT for simulator testing | `--reason "repro #88" --ttl 900` |
| `admin trace <cid>` | Fetch the full pipeline trace for one correlation ID | `--json` |
| `admin errors recent` | List the most recent captured error snapshots | `--module app.routers.chat --last 20` |
| `admin debug <verb>` | Legacy debug subcommands (lookup, requests, tokens, errors, modules, replay, generate-test) | see `admin debug --help` |
| `admin user search <q>` | Partial-match users by name/email | `--limit`, `--json` |
| `admin user ban <target> --reason "..."` | Ban user for N days (audited) | `--days`, `--json` |
| `admin user unban <target> --reason "..."` | Clear ban (audited) | `--json` |
| `admin user delete <target> --reason "..."` | Soft-delete user; refuses if active paid sub | `--json` |
| `admin user grant-admin <target> --reason "..."` | Flip is_admin=true | `--json` |
| `admin user revoke-admin <target> --reason "..."` | Flip is_admin=false | `--json` |
| `admin sub show <target>` | Show subscription state incl. Duo flag | `--json` |
| `admin sub list` | List/filter subscriptions | `--status`, `--expired-within`, `--limit`, `--json` |
| `admin sub grant <target> --tier pro --until YYYY-MM-DD --reason "..."` | Grant subscription (audited). Duo users require `--force-duo` | `--product-id`, `--json` |
| `admin sub extend <target> --days N --reason "..."` | Add days to expiry (audited) | `--force-duo`, `--json` |
| `admin sub revoke <target> --reason "..."` | Set status=expired (audited) | `--force-duo`, `--json` |
| `admin sub verify <target>` | Dry-run StoreKit diff (stub until Phase 4) | `--json` |
| `admin ops ratelimit clear --user <key>\|--all --reason "..."` | Wipe chat rate-limit buckets | `--json` |
| `admin ops session revoke <target> --reason "..."` | Force logout on all JWTs for user | `--json` |
| `admin ops flags list\|get\|set\|unset` | Read/write feature_flags table (auth_dev_enabled, broadcast_banner, ...) | `set <k> <json-value> --reason "..."`, `--json` |
| `admin ops cache flush --key <k> --reason "..."` | Stub (no Redis yet) | `--json` |
| `admin audit list` | Query admin_audit_log | `--since`, `--admin`, `--target-user`, `--action`, `--limit`, `--json` |
| `admin audit show <audit_id>` | Full audit row | `--json` |
| `admin audit prune --before 90d --reason "..."` | Manual retention (destructive, typed confirm) | `--yes`, `--json` |

### Common pitfalls

1. **`admin ping` returns 403** — Your stored token is from a user without `is_admin=True`. Run `admin whoami` to confirm, then ask a super-admin to set the flag or re-login.
2. **`admin user inspect` can't find the user** — `<target>` accepts email (partial match OK) or UUID. Partial email matching is case-insensitive but must be unambiguous; if two users match you'll get an error listing both.
3. **Token expired mid-session** — Admin JWTs have a 2 h TTL. Re-run `admin login` and retry the command.
4. **`admin debug` subcommands read Cloud Logging** — they require `gcloud auth login` and the right project set. If you see `gcloud: command not found`, install the Google Cloud SDK first.
- Duo subscribers require `--force-duo` on mutations — usually you should operate on the payer.
- `admin user delete` refuses if the user has an active paid subscription; revoke first.
- `admin ops flags set` parses the value as JSON (`true`, `false`, numbers, `{...}`, `[...]`); unquoted strings fall through unchanged.
- `admin audit prune` is destructive and bypasses dry-run; always use `--yes` explicitly.

<!-- /ai-cheatsheet -->

---

## Install and first run

```bash
# 1. Install the package (includes the `admin` console script)
cd /path/to/CozyPup
pip install -e backend

# 2. Log in against the local dev backend
#    Requires the backend to be running with ENVIRONMENT=dev
admin login --dev --email robert@example.com

# 3. Verify the session
admin whoami
# Expected output:
# admin: robert@example.com (uuid: 4f2a1c…)
# token expires: 2026-04-12 14:32:00 UTC
# env: dev  base_url: http://localhost:8000

# 4. Prod login uses OAuth (opens browser)
admin login --env prod
```

**Troubleshooting first run:** If `admin whoami` fails with "permission denied reading config", the config file has insecure permissions. Fix with:

```bash
chmod 600 ~/.cozypup/admin.json
```

The CLI refuses to read a config file that is world- or group-readable.

---

## Global flags

These flags work on every command and must appear **before** the subcommand name.

| Flag | Values | Description |
|------|--------|-------------|
| `--env` | `dev` \| `prod` | Override the environment for this invocation. Default: whatever is stored in `~/.cozypup/admin.json`. |
| `--json` | boolean flag | Emit raw JSON instead of pretty tables. Useful for piping to `jq`. |
| `--reason` | string | Human-readable reason string appended to `admin_audit_log`. Required for all write operations (export, impersonate). |
| `--out` | file path | Write output to a file instead of stdout. Supported by `user export` and `trace`. |

---

## Command reference

### Auth group: `login` / `logout` / `whoami` / `config`

#### `admin login [--dev] [--email <e>] [--env prod|dev]`

Authenticate and store a scoped admin JWT at `~/.cozypup/admin.json` (mode 0600). With `--dev` the CLI calls `POST /api/v1/admin/auth/dev-login` — no OAuth, just email + server-side `is_admin` check. Without `--dev`, the OAuth loopback flow is started (browser opens). The token is valid for 2 hours.

```
$ admin login --dev --email robert@example.com
Logged in as robert@example.com (is_admin=True)
Token stored at ~/.cozypup/admin.json (expires in 2h)
```

**Common errors:**
- `403 Forbidden` — user does not have `is_admin=True` in the database.
- `Connection refused` — backend is not running; start it with `uvicorn app.main:app --reload --port 8000`.

#### `admin logout`

Removes `~/.cozypup/admin.json`. Safe to run at any time; no server call is made.

#### `admin whoami`

Decodes and prints the stored JWT claims. Makes a live call to `/api/v1/admin/whoami` to confirm the server still accepts the token.

```
$ admin whoami
admin: robert@example.com (uuid: 4f2a1c8d-…)
token expires: 2026-04-12 14:32:00 UTC
env: prod  base_url: https://backend-601329501885.northamerica-northeast1.run.app
```

#### `admin config show|set`

`show` prints all stored config values. `set <key> <value>` persists a single key.

```
$ admin config set base_url http://localhost:8000
Config updated: base_url = http://localhost:8000
```

Valid keys: `base_url`, `env`, `default_reason`.

---

### `admin ping [--reason <r>]`

Sends `GET /api/v1/admin/ping` with the stored admin token. Verifies network reachability, TLS, and that the admin scope is accepted. Prints server version and uptime.

```
$ admin ping --reason "prod health check"
pong from backend v2.4.1 (uptime 3d 14h)
admin scope: OK  env: prod
```

**Common errors:**
- `401 Unauthorized` — token expired; re-run `admin login`.
- `403 Forbidden` — token valid but `is_admin=False`.

---

### User commands

#### `admin user inspect <target> [--chats N] [--errors] [--json]`

Prints a full snapshot of one user: account fields, pets (name, species, DOB), recent N chat messages (default 10), and an error summary if `--errors` is passed. `<target>` is an email (partial OK) or UUID.

```
$ admin user inspect alice@example.com --chats 5 --errors
User: alice@example.com  uuid: 8b3d…  created: 2025-11-02
Plans: pro  is_admin: False

Pets (2):
  Mochi    dog   golden_retriever   DOB 2022-03-15
  Luna     cat   domestic_shorthair DOB 2023-07-01

Recent chats (5):
  2026-04-12 09:14  "Is it normal for Mochi to skip breakfast?"   cid: 7a2f8b4c…
  2026-04-11 21:03  "Remind me to give Luna her flea meds Friday"  cid: 3c9e1a2d…
  …

Errors (last 24h): 0
```

#### `admin user export <target> --reason <r> [--out <path>]`

Generates a GDPR data bundle for the user: JSON export of all chats, pets, calendar events, and reminders. Writes a `.zip` to `--out` (defaults to `./cozypup-export-<uuid>.zip`). This is a write operation — `--reason` is required and is logged to `admin_audit_log`.

```
$ admin user export alice@example.com \
    --reason "GDPR deletion request #42" \
    --out /tmp/alice-export.zip
Exported 3 pets, 847 chats, 112 events → /tmp/alice-export.zip (214 KB)
Audit log entry: export  target: 8b3d…  by: robert@example.com
```

**Common errors:**
- `422` — `--reason` flag missing.
- `404` — user not found; double-check the email/UUID.

#### `admin user impersonate <target> --reason <r> [--ttl <seconds>]`

Mints a short-lived user JWT (default 900 s, max 900 s) for the target user. The token is printed to stdout — paste it into the simulator's `AuthStore` or use it with `curl -H "Authorization: Bearer <token>"`. This is a write operation; `--reason` is required.

```
$ admin user impersonate alice@example.com --reason "repro ticket #88"
Impersonation token (TTL 900s):
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI4YjNkLi…
Audit log entry: impersonate  target: 8b3d…  by: robert@example.com
```

**Common errors:**
- `403` — attempting to impersonate another admin is blocked.

---

### `admin trace <correlation-id> [--json] [--out <path>]`

Fetches the full pipeline trace for one request from Cloud Logging: `chat_request → llm_request → llm_response → tool_call → tool_result → chat_response`. Useful for understanding exactly what the LLM decided and which tools fired.

```
$ admin trace 7a2f8b4c-3f1e-4a2b-9c8d-1234567890ab
Trace: 7a2f8b4c…  user: alice@example.com  2026-04-12 09:14:03 UTC
  [0ms]  chat_request      "Is it normal for Mochi to skip breakfast?"
  [12ms] llm_request       model=grok-4-1-fast  tokens_in=1842
  [834ms] llm_response     tool_calls=[search_knowledge]
  [836ms] tool_call        search_knowledge  query="dog skip meals appetite"
  [941ms] tool_result      3 knowledge chunks returned
  [943ms] llm_request      (second pass)  tokens_in=2109
  [1201ms] llm_response    content="Occasional skipped meals…"
  [1202ms] chat_response   tokens_out=312  total_ms=1202
```

**Common errors:**
- Blank output — the correlation ID was from more than 30 days ago (Cloud Logging retention).
- `gcloud` auth error — run `gcloud auth login`.

---

### `admin errors recent [--module <mod>] [--last N]`

Lists the most recent error snapshots captured by the `ErrorCapture` middleware. Snapshots include request body, headers (redacted), exception traceback, and correlation ID for further tracing.

```
$ admin errors recent --module app.routers.chat --last 5
#  cid              module               error                          ts
1  7a2f8b4c…       app.routers.chat     ValueError: invalid pet_id     2026-04-12 08:55
2  3c9e1a2d…       app.routers.chat     TimeoutError: LLM upstream     2026-04-11 23:12
…
```

Use the `cid` values with `admin trace` to drill into the full request chain.

---

### `admin debug <legacy-verb>`

Rehomed wrapper for the original `debug` CLI commands. All subcommands are unchanged; they now live under `admin debug` to keep the namespace consistent.

Available subcommands:
- `admin debug lookup <email>` — find user_id by email
- `admin debug requests --user <user_id> --last N` — recent chat requests
- `admin debug tokens --user <user_id> --period 7d` — token usage summary
- `admin debug errors --module <mod> --last N` — error counts by module
- `admin debug modules --since 24h` — error counts grouped by module
- `admin debug replay <cid>` — replay a failed request
- `admin debug generate-test <cid>` — auto-generate a pytest from an error

Run `admin debug --help` or `admin debug <verb> --help` for per-command usage.

---

### Phase 2 — User & Subscription Management

#### `admin user search <q>`
Partial-match on `users.name` and `users.email`. Use this to resolve a UUID from a fuzzy name before piping into `inspect` or a write command.

Example:
```
$ admin user search 张
Users matching '张'
  zhangwei@example.com                   张伟                      id=8f3c...
  zhangna@example.com                    张娜                      id=42aa...
```

#### `admin user ban / unban`
Sets or clears `users.banned_until`. The auth middleware blocks all API requests for a banned user with 403 until the ban expires.

Example:
```
$ admin user ban alice@example.com --days 7 --reason "chat spam"
$ admin user unban alice@example.com --reason "appeal granted"
```

#### `admin user delete`
Soft-deletes: sets `deleted_at`, clears PII fields, and from then on the user gets 403 on every request. Refuses when the user has an active paid subscription — revoke the sub first.

#### `admin user grant-admin / revoke-admin`
Flips the `is_admin` flag on the target. After grant, the new admin must log out and back in with `admin login` to get an admin-scoped JWT.

#### `admin sub show / list`
Read-only views. `list` supports `--status active|expired|trial` and `--expired-within 7d` for "find customers whose subscription lapsed in the last week".

#### `admin sub grant / extend / revoke`
All write through `@audit_write`. `extend --days N` is the common refund path. `grant --tier pro --until YYYY-MM-DD` is the beta-tester path. Duo-plan mutations print a warning and require `--force-duo`.

#### `admin sub verify`
Phase 2 ships this as a stub that returns the current DB state with a `match: true` placeholder. Phase 4 will wire it to the real StoreKit verification endpoint.

### Phase 3 — Ops, Flags, Audit

#### `admin ops ratelimit clear`
The chat rate limiter holds per-user buckets in memory. Use `--user <key>` to wipe one bucket or `--all` to wipe them all. The `user_key` is the last 16 chars of the user's access token (see the middleware source).

#### `admin ops session revoke <target>`
Inserts a row into `token_revocation` so `verify_token` rejects any JWT whose `iat` predates the revocation timestamp. Effectively a "force logout" across all devices.

#### `admin ops flags list / get / set / unset`
Feature flag CRUD. Values are stored as JSONB and parsed as JSON on the way in:

```
admin ops flags set auth_dev_enabled false --reason "killing dev auth in prod"
admin ops flags set broadcast_banner '{"text":"maintenance at 10pm","severity":"info"}' --reason "scheduled maint"
admin ops flags set chat_rate_limit_per_hour 60 --reason "raising to 60/hr"
```

Initial flag inventory:
- `auth_dev_enabled` (bool) — gates `POST /api/v1/auth/dev`. Default `true` in dev, should be explicitly set to `false` in prod.
- `chat_rate_limit_per_hour` (int) — override the default 30/hr in the rate-limit middleware.
- `broadcast_banner` (object) — iOS app reads this from `GET /api/v1/flags/public` and shows a banner.

#### `admin ops cache flush --key <k>`
Stub. Logs the request and returns `{"stub": true}`. When Redis is added later the command already has the shape; no CLI change needed.

#### `admin audit list / show / prune`
`list` supports filters by `--since`, `--admin <email>`, `--target-user <id>`, and `--action`. `show <audit_id>` prints the full row (args + result diff). `prune --before 90d --reason "..."` deletes old rows; use `--yes` to skip confirmation.

---

## Scenario playbooks

### 1. "A user reported the app crashed after sending an image"

```bash
# Step 1: find the user and get a sense of recent errors
admin user inspect alice@example.com --errors --chats 10

# Step 2: grab the correlation ID from the failing chat row, then trace it
admin trace 7a2f8b4c-3f1e-4a2b-9c8d-1234567890ab

# Step 3: if the trace shows an unhandled exception, get the full snapshot
admin errors recent --module app.routers.chat --last 10

# Step 4: replay the request locally to confirm the fix
admin debug replay 7a2f8b4c-3f1e-4a2b-9c8d-1234567890ab
```

### 2. "A developer needs to reproduce a user bug locally"

```bash
# Step 1: mint a short-lived token for the affected user
admin user impersonate alice@example.com \
  --reason "repro ticket #88 - chat crash on image upload"

# Step 2: the printed JWT is valid for 15 min
# Paste it into AppConfig.swift (devToken) or set it in the simulator's
# AuthStore via the debug menu, then reproduce the steps.

# Step 3: capture the new correlation ID from the simulator console,
# then trace it to confirm the fix
admin trace <new-cid-from-simulator>
```

### 3. "GDPR data export request"

```bash
# Export the full data bundle for the requesting user
admin user export alice@example.com \
  --reason "GDPR Art. 20 portability request ticket #42" \
  --out /tmp/alice-export-2026-04-12.zip

# Verify the bundle is non-empty before handing over
unzip -l /tmp/alice-export-2026-04-12.zip
```

The zip contains `chats.json`, `pets.json`, `calendar_events.json`, and `reminders.json`. Confirm with your legal process before delivery.

### 4. "Post-incident review: errors in the last 24h"

```bash
# Step 1: get error counts by module
admin debug modules --since 24h
# Output shows which modules had the most errors

# Step 2: drill into the noisiest module
admin errors recent --module app.routers.chat --last 20

# Step 3: for each suspicious correlation ID, inspect the user and full trace
admin user inspect alice@example.com --chats 5 --errors
admin trace 3c9e1a2d-…
```

### 5. Customer support: refund a month

```bash
admin sub show alice@example.com                        # verify state, check for Duo
admin sub extend alice@example.com --days 30 --reason "support ticket #4521"
admin audit list --target-user alice@example.com --since 1d   # confirm the row landed
```

### 6. Incident response: kill `/auth/dev` in prod immediately

```bash
admin ops flags set auth_dev_enabled false --reason "incident: suspicious dev-login traffic" --env prod
# Verify the backend picks it up within ~30s (flag cache TTL):
curl -X POST https://backend-601329501885.northamerica-northeast1.run.app/api/v1/auth/dev -d '{"email":"x@y.com"}'
# → expect 404
admin audit list --action ops.flags.set --since 1h
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `401 Unauthorized` on any command | Admin token expired (2 h TTL). Run `admin login` again. |
| `Error: ~/.cozypup/admin.json must be mode 0600` | `chmod 600 ~/.cozypup/admin.json` |
| `gcloud: command not found` or `gcloud auth error` | Install Google Cloud SDK, then: `gcloud auth login && gcloud config set project cozypup-39487` |
| `404 Not Found` on `/api/v1/admin/*` | Either not logged in, the backend doesn't have the admin router registered, or `is_admin=False`. Run `admin whoami` to confirm identity. |
| `422 Unprocessable Entity` on export or impersonate | `--reason` flag is missing — it is required for all write operations. |
| `admin debug` commands hang | These call `gcloud logging read` as a subprocess. Ensure `gcloud` is on `$PATH` and the project is set correctly. |

---

## Security notes

- **Admin JWT TTL is 2 hours.** Tokens are scoped with `scope="admin"` and are verified separately from user JWTs. They cannot be used to call user-facing endpoints.
- **Impersonation tokens are capped at 15 minutes (900 s).** The server enforces this cap regardless of the `--ttl` value passed; it cannot be raised via the CLI.
- **Every write is audited.** Export and impersonate calls insert a row into `admin_audit_log` inside the same database transaction. The log records admin identity, target, reason, args, result, and source IP.
- **Dev-login is disabled in production.** `POST /api/v1/admin/auth/dev-login` is only available when `ENVIRONMENT=dev`. In production, authentication goes through the OAuth loopback flow.
- **Config file is 0600-enforced.** The CLI will refuse to read `~/.cozypup/admin.json` if its permissions are looser than owner-read-write-only.
