# Settings & Profile Redesign

**Date:** 2026-04-12
**Scope:** A (API surface) + B (frontend IA) + C (notifications)
**Out of scope:** D (remote-managed legal content)

## Problem

The Settings drawer and Profile sheet have grown organically and now have three classes of problems:

1. **Apple compliance gaps.** We have an auto-renewable subscription but ship without **Restore Purchases**, **Manage Subscription**, or **Terms of Use** — all hard requirements in App Store Review Guidelines 3.1.1 / 3.1.2(a). A review would likely reject the build.
2. **Dead / fake controls.** The three notification toggles (push / med reminders / weekly insights) persist only to `UserDefaults` and are never read by the backend. They look functional but do nothing. `phone_number` is returned by `GET /auth/me` and never used by any view.
3. **Architectural debt.** `GET /auth/me` does not return `avatar_url` (silently works today only because we pull the avatar off the login response and cache it). There is no way to change your own avatar after sign-in. Subscription has two entry points (Settings "Subscription" row + Profile "Duo Plan" row), Legal copy is hardcoded Swift strings, and the version label is the literal string `"CozyPup v1.0"`.

This redesign fixes compliance, removes dead controls, and re-homes every button into a clear Settings (app behavior) vs Profile (identity + subscription + legal) split.

## Information Architecture

**Rule:** Profile = things about *me as a person*. Settings = things about *how this app behaves*.

Consequences:
- Subscription lives only in Profile (it's tied to the person, not the device).
- Log Out lives in Settings (it's a device-level action — you're logging *this app* out).
- Delete Account lives in Profile (it's a person-level action — the account itself).
- The Profile entry from Settings is a header card at the top of Settings that pushes into the Profile sheet.

## Profile Sheet (`UserProfileSheet`)

```
[Avatar + Name (tap avatar → photo picker; tap name → edit inline)]

ACCOUNT
  Email
  Sign-in method

SUBSCRIPTION
  Current plan / Trial status       (read-only row)
  Manage Subscription               → SKShowManageSubscriptions
  Restore Purchases                 → StoreKit restore flow
  DUO PLAN · Active | Inactive      (section header, not a button)
    └─ [Friend avatar] Friend name   → FamilySettingsView
                      "Member" (if I am payer) / "Paid by" (if I am member)
    └─ [Invite pending placeholder] (only if I am payer with pending invite)
    └─ "Upgrade to Duo Plan"         → PaywallSheet(initialDuo: true)
                                       (only if NOT in Duo at all)

LEGAL
  Privacy Policy                    → SFSafariViewController (remote URL)
  Terms of Use                      → SFSafariViewController (remote URL)
  Disclaimer                        → in-app static page
  Acknowledgements                  → in-app static list of dependencies

[Delete Account]                    (red, bottom, confirmation alert)
```

**Duo Plan row behavior:**
- Section header shows `"DUO PLAN · Active"` or `"DUO PLAN · Inactive"`, never tappable.
- When Duo is active, exactly one row below the header is the tappable entry into `FamilySettingsView`: the friend's avatar + name + role subtitle.
- Subtitle: if current user is the `payer`, the friend row shows `"Member"`. If current user is the `member`, the friend row shows `"Paid by"`.
- When current user is the payer and an invite is pending (not yet accepted), show a placeholder row `"Invite pending..."` with a muted tertiary color — still taps into `FamilySettingsView` so the payer can revoke the invite.
- When Duo is inactive, show a single `"Upgrade to Duo Plan"` row that opens `PaywallSheet(initialDuo: true)`.

**Avatar editability:**
- Initial source: Google profile photo (synced on login, already implemented).
- User can tap their avatar on the Profile sheet → `PhotosPicker` → upload → avatar refreshes.
- Backend endpoint: `POST /api/v1/auth/me/avatar` — multipart image upload, writes to the existing `cozypup-avatars` GCS bucket, returns the new `avatar_url`.
- After upload, `AuthStore.user.avatarUrl` is updated and cached to `UserDefaults`.

## Settings Drawer (`SettingsDrawer`)

```
[User card header → opens UserProfileSheet]

MY PETS
  Pet list (add / edit / delete, existing QR co-own scan entry preserved)

PREFERENCES
  Language                          (Picker: 中文 / English)
  Sync to Apple Calendar            (existing EventKit flow)

NOTIFICATIONS
  Push Notifications                → UIApplication.openNotificationSettingsURLString

SUPPORT
  Contact Support                   → mailto: <TBD>
  Report a Problem                  → mailto: <TBD> with prefilled subject [Report] <version> <build> and device info body
  Rate CozyPup                      → SKStoreReviewController.requestReview()
  Share CozyPup                     → UIActivityViewController with App Store URL (<TBD>)

ABOUT
  What's New                        → static ReleaseNotes view
  Version X.Y.Z (build N)           → read from Bundle.main

[Log Out]                           (red, bottom)
```

## What Gets Removed

- Settings row **"Subscription"** — moves into Profile sheet under SUBSCRIPTION.
- Three notification toggles **push / med reminders / weekly insights** and their `cozypup_notification_prefs` `UserDefaults` key. Replaced by a single "Push Notifications" row that opens system settings (iOS 16+ `UIApplication.openNotificationSettingsURLString` deep-links into this app's notification settings).
- Hardcoded `"CozyPup v1.0"` literal — replaced with `Bundle.main.infoDictionary["CFBundleShortVersionString"]` + `CFBundleVersion`.
- Hardcoded privacy / disclaimer / about strings in `UserProfileSheet` are removed where URL-backed; Disclaimer and Acknowledgements remain in-app.

## Backend API Changes

Only two real changes. Everything else (Manage Subscription, Restore, Rate, Share, Report, Terms URL, notification deep-link) is pure client work.

### 1. `GET /api/v1/auth/me` — add `avatar_url`

Current response:
```json
{ "id", "email", "name", "auth_provider", "phone_number" }
```

New response:
```json
{ "id", "email", "name", "avatar_url", "auth_provider", "phone_number" }
```

`avatar_url` is nullable (empty string → `null`). No migration — the column already exists on the `User` model.

**Why:** fixes an existing bug where the avatar is only populated from the login response; any flow that refetches the user (e.g., after name edit) currently drops the avatar.

### 2. `POST /api/v1/auth/me/avatar` — new endpoint

- **Request:** `multipart/form-data` with a single `file` field (image, max 5 MB, jpeg/png/heic).
- **Response:** `{ "avatar_url": "<public GCS URL>" }`
- **Storage:** existing `cozypup-avatars` GCS bucket, object key `users/<user_id>/<timestamp>.<ext>`, public-read ACL (bucket is already configured this way for pet avatars).
- **Side effect:** updates `User.avatar_url`, commits, returns.
- **Auth:** `get_current_user_id` dependency.
- **Validation:** content-type check, size check; reject with 400 on violation.

### 3. `PATCH /api/v1/auth/me` — unchanged

Continues to accept only `name`. Avatar goes through the new dedicated endpoint, not `PATCH`.

### 4. `phone_number` — untouched

Stays on the model, stays in the `GET /auth/me` response, no UI surfaces it. Reserved for future SMS/push channel.

## Scope C: Notifications

Decision: single "Push Notifications" row that deep-links to system settings (iOS `UIApplication.openNotificationSettingsURLString`, iOS 16+).

Rationale:
1. Push notifications are a Phase 4 TODO — there is no backend push infrastructure yet.
2. Modeling granular preferences now is building data for a feature that doesn't exist.
3. The iOS platform convention is to route notification-level control to system settings; a single deep-link row matches user expectation.
4. If future requirements show a real need for granular toggles, re-open this decision with actual push-sending code in hand.

The `cozypup_notification_prefs` UserDefaults key is deleted and not migrated — no one is reading it.

## Legal / Support Content Source

- **Privacy Policy URL:** `<TBD>` — opens in `SFSafariViewController`.
- **Terms of Use URL:** `<TBD>` — opens in `SFSafariViewController`.
- **Disclaimer:** remains in-app, hardcoded markdown-ish text. This is product-level disclaimer copy (not a legal contract) and rarely changes.
- **Acknowledgements:** in-app static view; hand-maintained list of third-party dependencies.
- **What's New:** in-app `ReleaseNotes.swift` with the last 3 versions, bumped by hand at each release.
- **Support email:** `<TBD>` — used by both Contact Support and Report a Problem.
- **App Store share URL:** `<TBD>` — used by Share CozyPup.

All four `<TBD>` values are tracked in one place (see Placeholders section) and filled in before the first App Store submission.

## Placeholders (must fill before App Store submission)

| Placeholder | Used by | Suggested default |
|---|---|---|
| `SUPPORT_EMAIL` | Contact Support, Report a Problem | `support@cozypup.app` |
| `PRIVACY_POLICY_URL` | Profile → Privacy Policy | `https://cozypup.app/privacy` |
| `TERMS_OF_USE_URL` | Profile → Terms of Use | `https://cozypup.app/terms` |
| `APP_STORE_URL` | Share CozyPup | (app-specific, fill at submission time) |

These live as constants in a single `AppConfig.swift` file, not scattered across views. Share CozyPup is disabled until `APP_STORE_URL` is non-empty.

## Verification (QA Matrix)

Every button and navigation must be explicitly verified before shipping. The implementation plan will produce this matrix as a filled-out table.

### 1. Button → API / Action mapping

| Button | Expected action | How to verify |
|---|---|---|
| Profile card (Settings header) | Opens `UserProfileSheet` | Tap; sheet presents |
| Avatar (Profile) | Opens `PhotosPicker` → `POST /auth/me/avatar` → refresh | Tap; pick image; network request visible; avatar updates |
| Name (Profile) | `PATCH /auth/me` with new name | Edit; submit; name persists after dismiss |
| Manage Subscription | `SKShowManageSubscriptions` | Tap; system sheet appears |
| Restore Purchases | StoreKit restore | Tap; entitlements refresh |
| Duo Plan friend row | Pushes `FamilySettingsView` | Tap; view presents |
| Upgrade to Duo | `PaywallSheet(initialDuo: true)` | Tap; paywall in Duo mode |
| Privacy Policy | `SFSafariViewController(PRIVACY_POLICY_URL)` | Tap; Safari in-app |
| Terms of Use | `SFSafariViewController(TERMS_OF_USE_URL)` | Tap; Safari in-app |
| Disclaimer | In-app static page | Tap; page presents |
| Acknowledgements | In-app static list | Tap; list presents |
| Delete Account | `DELETE /auth/me` + logout | Tap; confirm; account gone |
| Add / Edit / Delete Pet | `POST/PATCH/DELETE /pets/*` | Existing flows regression-tested |
| Language picker | `Lang.shared.code` | Change; UI strings update |
| Sync to Apple Calendar | `CalendarSyncService` | Existing flow regression-tested |
| Push Notifications | `UIApplication.open(notificationSettingsURL)` | Tap; system settings opens at this app |
| Contact Support | `mailto:SUPPORT_EMAIL` | Tap; Mail compose appears |
| Report a Problem | `mailto:` with prefilled subject + body | Tap; Mail compose with metadata |
| Rate CozyPup | `SKStoreReviewController.requestReview()` | Tap; review prompt |
| Share CozyPup | `UIActivityViewController` with `APP_STORE_URL` | Tap; share sheet |
| What's New | Static `ReleaseNotes` view | Tap; page presents |
| Version label | Reads from `Bundle.main` | Matches `Info.plist` |
| Log Out | Clears token, dismisses drawer | Tap; returns to login |

### 2. Navigation smoke test

- Settings → Profile card → Profile sheet → Delete Account alert → cancel → still in Profile sheet
- Settings → Profile → Duo Plan friend row → FamilySettingsView → back → Profile
- Settings → Profile → Privacy Policy → SFSafari → done → Profile
- Settings → Pet edit → QR share → scanner → cancel → Pet edit → back → Settings
- Settings → Log Out → login screen
- Profile → Delete Account → confirm → login screen

### 3. Design token audit

Checklist against `CLAUDE.md` Design System rules — grep the diff for violations:
- No hardcoded `Color(...)` literals — all colors via `Tokens.*`
- No `.foregroundColor(.white)` / `.black` — use `Tokens.white`, `Tokens.text`
- No hardcoded font sizes — all fonts via `Tokens.fontX`
- No hardcoded spacing numbers — all spacing via `Tokens.spacing.*`
- No hardcoded corner radii — all via `Tokens.radius*`
- Every new / modified view has a `#Preview` block
- Text color contrast: all destructive actions use `Tokens.red`; all primary actions `Tokens.accent`; all secondary text `Tokens.textSecondary` / `Tokens.textTertiary`

### 4. Backend tests

- `GET /auth/me` returns `avatar_url` (new field present, nullable)
- `POST /auth/me/avatar` — happy path (image uploads, URL returned, DB updated)
- `POST /auth/me/avatar` — oversize rejection
- `POST /auth/me/avatar` — wrong content-type rejection
- `POST /auth/me/avatar` — unauthenticated rejection

## Out of Scope (explicitly)

- Remote-managed legal content (scope D) — Privacy / Terms are URL-backed but served by a static site (GitHub Pages, Notion, etc.) outside the CozyPup backend.
- Granular notification preferences with backend persistence — deferred until real push infrastructure exists.
- Theme toggle, biometric lock, data export, clear cache — not on roadmap.
- `phone_number` UI — field stays on the model but has no surface.
- Open-source license auto-generation — hand-maintained for now.

## Execution Note

The implementation plan should structure this work for agent-team execution with inline communication:
- Backend (endpoints + tests) and iOS (views + wiring) can proceed in parallel up to the integration point.
- The QA matrix above must be filled out as the verification step — not just "tests pass" but an explicit per-button walk.
- Checkpoints between agents: after backend endpoints land, iOS integrates; after iOS integration, full QA matrix pass; after QA, document review of design tokens.

The writing-plans skill (next step) is responsible for turning this into concrete subagent-driven tasks with blockers and checkpoints.
