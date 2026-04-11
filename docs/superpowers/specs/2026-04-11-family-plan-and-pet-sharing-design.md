# Family Plan & Pet Sharing Design

## Overview

Two independent features that work together:
1. **Family Plan (Duo)** — One person pays, two people get full membership
2. **Pet Sharing** — Two users share a pet's data (diary, reminders, photos) via QR code

## 1. Family Plan (Duo)

### Pricing

| Plan | Individual | Duo |
|------|-----------|-----|
| Weekly | CA$1.99 | CA$2.99 |
| Monthly | CA$6.99 | CA$9.99 |
| Yearly | CA$59.99 | CA$84.99 |

Product IDs:
- `com.cozypup.app.weekly` / `com.cozypup.app.weekly.duo`
- `com.cozypup.app.monthly` / `com.cozypup.app.monthly.duo`
- `com.cozypup.app.yearly` / `com.cozypup.app.yearly.duo`

### Invite Flow

1. Payer upgrades to Duo plan in Settings
2. Settings page shows "Invite Partner" button
3. Payer enters partner's email → backend sends invite email
4. Partner clicks email link → opens app → auto-accepts invite
5. Partner's `subscription_status` set to `"active"`, linked to payer

### Upgrade (Individual → Duo)

- Must stay on same billing cycle (weekly→weekly, monthly→monthly)
- Pro-rated: `upgrade_cost = (duo_price - individual_price) × (remaining_days / cycle_days)`
- Example: weekly individual $1.99, 3 days left → ($2.99 - $1.99) × 3/7 = $0.43
- Current cycle continues (not reset), next renewal at duo price

### Downgrade (Duo → Individual)

- Payer downgrades to individual plan
- Partner's `subscription_status` → `"expired"`
- Partner receives notification
- Shared pets enter the Pet Sharing unlink flow (see section 2)
- Partner can still READ data but cannot modify until they get their own subscription

### Data Model Changes

```
FamilyInvite table:
  id: UUID (PK)
  inviter_id: UUID (FK → users.id)     — the payer
  invitee_email: String
  invitee_id: UUID (FK → users.id)     — null until accepted
  status: "pending" | "accepted" | "revoked"
  created_at: DateTime
  accepted_at: DateTime (nullable)

User table additions:
  family_role: "payer" | "member" | null
  family_payer_id: UUID (FK → users.id, nullable)  — for members, points to payer
```

### Constraints

- One payer can invite exactly 1 person (duo = 2 people total)
- A person can only be a member of one family
- Payer cannot be a member of someone else's family
- Revoking invite → partner loses membership immediately

## 2. Pet Sharing

### Share Flow (QR Code)

1. A opens pet detail page → taps "Share" → generates QR code
   - QR encodes: `cozypup://share?pet_id=<uuid>&token=<one-time-token>`
   - Token expires in 10 minutes
2. B scans QR code → app opens share acceptance screen
3. If B has pets:
   - Show B's pet list as cards (avatar + name)
   - B can select one to merge, or skip (no merge)
4. If B selects a pet to merge → execute merge (see below)
5. If B skips → A's pet is added to B's pet list as a shared pet

### Merge Logic

When B selects their pet to merge with A's:

**Structured fields** (weight, birthday, breed, species, gender, avatar):
- Keep A's values (share initiator is the source of truth)

**profile_md** (narrative document):
- Call LLM to read both documents and produce a merged version
- Prompt: "Merge these two pet profiles. Keep all unique information from both. When conflicting, prefer Profile A. Output a single cohesive markdown document."

**Calendar events / diary entries**:
- Move all of B's pet events to A's pet (update `pet_id`)
- Set `created_by = B.user_id` on moved records to track authorship

**Reminders**:
- Move all of B's pet reminders to A's pet (update `pet_id`)

**Photos**:
- Move all photo references

**After merge**:
- Delete B's duplicate Pet record
- B now sees A's pet (with all merged data) in their pet list

### Data Model Changes

```
PetCoOwner table:
  id: UUID (PK)
  pet_id: UUID (FK → pets.id)
  user_id: UUID (FK → users.id)        — the co-owner (not the original owner)
  role: "co_owner"                      — extensible for future roles
  created_at: DateTime

PetShareToken table:
  id: UUID (PK)
  pet_id: UUID (FK → pets.id)
  owner_id: UUID (FK → users.id)       — who generated the QR
  token: String (unique, 32 chars)
  expires_at: DateTime                  — 10 min TTL
  used: Boolean (default false)

CalendarEvent table additions:
  created_by: UUID (FK → users.id, nullable)  — who recorded this event

Reminder table additions:
  created_by: UUID (FK → users.id, nullable)
```

### Query Changes

All pet-related queries need to check BOTH:
- `Pet.user_id == current_user` (original owner)
- `PetCoOwner.user_id == current_user` (co-owner)

This affects: pets router, calendar router, reminders router, chat agent tools, ownership validation.

### Unshare Flow

B taps "Leave Shared Pet" → choice screen:

**Option 1: Keep a copy**
- Deep copy the pet: new Pet record for B with all current data
- Copy all calendar events, reminders, photos (new records, same content)
- Copy profile_md as-is
- B's copy is fully independent, no longer synced

**Option 2: Just leave**
- Remove B from PetCoOwner
- Pet disappears from B's list
- All data stays on A's pet (including events B created)

A (original owner) is not affected in either case.

### Triggered by Family Plan Downgrade

When payer downgrades from Duo → Individual:
1. Partner's subscription expires
2. For each pet shared between payer and partner:
   - Partner enters the unshare flow (keep copy or leave)
3. Partner's copied pets become read-only (expired subscription)

## 3. API Endpoints

### Family Plan
- `POST /api/v1/family/invite` — send invite email `{email: string}`
- `POST /api/v1/family/accept` — accept invite `{invite_id: string}`
- `POST /api/v1/family/revoke` — payer revokes partner
- `GET /api/v1/family/status` — current family info (partner, role)
- `POST /api/v1/subscription/upgrade` — upgrade individual → duo `{target_product_id: string}`

### Pet Sharing
- `POST /api/v1/pets/{pet_id}/share-token` — generate QR token
- `POST /api/v1/pets/accept-share` — accept share `{token: string, merge_pet_id?: string}`
- `POST /api/v1/pets/{pet_id}/unshare` — leave shared pet `{keep_copy: boolean}`
- `GET /api/v1/pets` — updated to include co-owned pets

## 4. iOS Changes

### Settings Page
- "Duo Plan" section: upgrade button, invite partner (email input), current partner info
- If member: show "You're on X's family plan"

### Pet Detail Page
- "Share" button → QR code sheet
- If co-owned: show co-owner avatar, "Leave" button

### Share Acceptance Screen
- Triggered by QR scan / deep link
- Shows sharer's pet card
- "Merge with your pet?" → pet list cards
- "Skip" → add directly
- Confirm button

### Unshare Screen
- "Keep a copy" / "Just leave" choice
- Confirmation dialog

## 5. Edge Cases

- B scans expired QR token → show "Link expired, ask them to generate a new one"
- B scans but already co-owns this pet → show "You already share this pet"
- A deletes the pet while B co-owns it → pet removed from both, B gets notification
- Both A and B try to edit the same event simultaneously → last-write-wins (no conflict resolution needed for MVP)
- B is not a registered user yet → invite email includes app download link, share token saved for post-registration
