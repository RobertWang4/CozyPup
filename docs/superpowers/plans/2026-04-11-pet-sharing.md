# Pet Sharing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow two users to share a pet via QR code, with data merging and bidirectional sync.

**Architecture:** Add PetCoOwner junction table and PetShareToken table. Modify all pet ownership queries to include co-owners. Share flow: owner generates time-limited token → co-owner scans → optional merge with existing pet → both see the same pet data. Unshare: co-owner can keep a deep copy or just leave.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, iOS SwiftUI (QR generation + camera scan)

**Spec:** `docs/superpowers/specs/2026-04-11-family-plan-and-pet-sharing-design.md` (Section 2)

---

### Task 1: Database Models & Migration

**Files:**
- Modify: `backend/app/models.py` — add PetCoOwner, PetShareToken, add created_by to CalendarEvent/Reminder
- Create: `backend/alembic/versions/xxxx_add_pet_sharing.py`

- [ ] **Step 1: Add models**

In `backend/app/models.py`, add after FamilyInvite (or after Pet):

```python
class PetCoOwner(Base):
    __tablename__ = "pet_co_owners"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pets.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("pet_id", "user_id"),)


class PetShareToken(Base):
    __tablename__ = "pet_share_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pets.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

Add `created_by` to CalendarEvent and Reminder models:

```python
# In CalendarEvent class, add:
created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

# In Reminder class, add:
created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
```

Also add `UniqueConstraint` import at top if not present:
```python
from sqlalchemy import UniqueConstraint
```

- [ ] **Step 2: Generate and apply migration**

```bash
cd backend && source .venv/bin/activate
alembic revision --autogenerate -m "add pet sharing tables"
alembic upgrade head
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/
git commit -m "feat: add PetCoOwner, PetShareToken models and created_by fields"
```

---

### Task 2: Pet Ownership Helper

**Files:**
- Create: `backend/app/agents/tools/ownership.py` — shared helper for checking ownership + co-ownership

- [ ] **Step 1: Write test**

Create `backend/tests/test_pet_ownership.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.models import Pet, PetCoOwner


@pytest.mark.asyncio
async def test_can_access_own_pet():
    from app.agents.tools.ownership import can_access_pet
    user_id = uuid4()
    pet = MagicMock(spec=Pet)
    pet.id = uuid4()
    pet.user_id = user_id

    db = AsyncMock()
    # Return pet for owner query
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = pet
    db.execute.return_value = result_mock

    found = await can_access_pet(db, str(pet.id), user_id)
    assert found is not None
    assert found.id == pet.id
```

- [ ] **Step 2: Implement helper**

Create `backend/app/agents/tools/ownership.py`:

```python
"""Unified pet ownership check — supports both owners and co-owners."""

import uuid

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Pet, PetCoOwner


async def can_access_pet(
    db: AsyncSession, pet_id: str, user_id: uuid.UUID
) -> Pet | None:
    """Check if user owns or co-owns the pet. Returns Pet or None."""
    pid = uuid.UUID(pet_id)
    # Check direct ownership
    result = await db.execute(
        select(Pet).where(Pet.id == pid, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if pet:
        return pet

    # Check co-ownership
    co_result = await db.execute(
        select(Pet)
        .join(PetCoOwner, PetCoOwner.pet_id == Pet.id)
        .where(Pet.id == pid, PetCoOwner.user_id == user_id)
    )
    return co_result.scalar_one_or_none()


async def get_user_pets(db: AsyncSession, user_id: uuid.UUID) -> list[Pet]:
    """Get all pets a user owns or co-owns, ordered by created_at."""
    # Owned pets
    owned_q = await db.execute(
        select(Pet).where(Pet.user_id == user_id).order_by(Pet.created_at)
    )
    owned = list(owned_q.scalars().all())

    # Co-owned pets
    co_q = await db.execute(
        select(Pet)
        .join(PetCoOwner, PetCoOwner.pet_id == Pet.id)
        .where(PetCoOwner.user_id == user_id)
        .order_by(Pet.created_at)
    )
    co_owned = list(co_q.scalars().all())

    # Deduplicate (shouldn't happen but safety)
    seen = {p.id for p in owned}
    for p in co_owned:
        if p.id not in seen:
            owned.append(p)
            seen.add(p.id)

    return owned
```

- [ ] **Step 3: Run test**

```bash
pytest tests/test_pet_ownership.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/agents/tools/ownership.py backend/tests/test_pet_ownership.py
git commit -m "feat: add unified pet ownership helper supporting co-owners"
```

---

### Task 3: Update Pet Router to Include Co-Owned Pets

**Files:**
- Modify: `backend/app/routers/pets.py` — use `get_user_pets()` for list, `can_access_pet()` for single

- [ ] **Step 1: Update list_pets endpoint**

In `backend/app/routers/pets.py`, replace the query in `list_pets`:

```python
from app.agents.tools.ownership import get_user_pets, can_access_pet

@router.get("", response_model=list[PetResponse])
async def list_pets(
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    pets = await get_user_pets(db, user_id)
    return [_pet_to_response(p) for p in pets]
```

- [ ] **Step 2: Update get_pet, update_pet, delete_pet to use can_access_pet**

Replace `select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)` patterns with `can_access_pet(db, pet_id, user_id)` in each endpoint.

- [ ] **Step 3: Run existing pet tests**

```bash
pytest tests/ -k "pet" -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/pets.py
git commit -m "feat: update pet router to include co-owned pets"
```

---

### Task 4: Update Agent Tools Ownership Checks

**Files:**
- Modify: `backend/app/agents/tools/pets.py` — replace `verify_pet_ownership` calls with `can_access_pet`

- [ ] **Step 1: Update verify_pet_ownership to use new helper**

Replace the existing `verify_pet_ownership` function in `backend/app/agents/tools/pets.py`:

```python
from app.agents.tools.ownership import can_access_pet

async def verify_pet_ownership(
    db: AsyncSession, pet_id: str, user_id: uuid.UUID
) -> Pet | None:
    """Verify pet belongs to user (owner or co-owner). Returns Pet or None."""
    return await can_access_pet(db, pet_id, user_id)
```

- [ ] **Step 2: Run agent tests**

```bash
pytest tests/test_ownership.py tests/test_tool_registry.py -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/agents/tools/pets.py
git commit -m "feat: update agent tools to support pet co-owners"
```

---

### Task 5: Pet Share Router

**Files:**
- Create: `backend/app/routers/pet_sharing.py`
- Modify: `backend/app/main.py` — register router

- [ ] **Step 1: Create pet sharing endpoints**

Create `backend/app/routers/pet_sharing.py`:

```python
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.models import (
    Pet, PetCoOwner, PetShareToken,
    CalendarEvent, Reminder,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/pets", tags=["pet-sharing"])

TOKEN_TTL_MINUTES = 10


class ShareTokenResponse(BaseModel):
    token: str
    expires_at: str


class AcceptShareRequest(BaseModel):
    token: str
    merge_pet_id: str | None = None  # B's pet to merge, or null to skip


class UnshareRequest(BaseModel):
    keep_copy: bool = False


@router.post("/{pet_id}/share-token", response_model=ShareTokenResponse)
async def create_share_token(
    pet_id: str,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Generate a QR share token for a pet. Owner only."""
    pid = uuid.UUID(pet_id)
    pet_q = await db.execute(
        select(Pet).where(Pet.id == pid, Pet.user_id == user_id)
    )
    pet = pet_q.scalar_one_or_none()
    if not pet:
        raise HTTPException(404, detail="Pet not found or not owner")

    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)

    share_token = PetShareToken(
        pet_id=pid,
        owner_id=user_id,
        token=token,
        expires_at=expires,
    )
    db.add(share_token)
    await db.commit()

    return ShareTokenResponse(token=token, expires_at=expires.isoformat())


@router.post("/accept-share")
async def accept_share(
    req: AcceptShareRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Accept a pet share. Optionally merge with an existing pet."""
    # Validate token
    token_q = await db.execute(
        select(PetShareToken).where(
            PetShareToken.token == req.token,
            PetShareToken.used == False,
        )
    )
    share_token = token_q.scalar_one_or_none()
    if not share_token:
        raise HTTPException(404, detail="Invalid or used share token")

    if datetime.now(timezone.utc) > share_token.expires_at:
        raise HTTPException(410, detail="Share token expired")

    # Can't share with yourself
    if share_token.owner_id == user_id:
        raise HTTPException(400, detail="Cannot share with yourself")

    # Check if already co-owner
    existing = await db.execute(
        select(PetCoOwner).where(
            PetCoOwner.pet_id == share_token.pet_id,
            PetCoOwner.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, detail="Already sharing this pet")

    # Mark token as used
    share_token.used = True

    # Create co-owner record
    co_owner = PetCoOwner(
        pet_id=share_token.pet_id,
        user_id=user_id,
    )
    db.add(co_owner)

    # If merge requested, merge B's pet into A's pet
    if req.merge_pet_id:
        await _merge_pets(db, share_token.pet_id, uuid.UUID(req.merge_pet_id), user_id)

    await db.commit()

    logger.info("pet_share_accepted", extra={
        "pet_id": str(share_token.pet_id),
        "owner_id": str(share_token.owner_id),
        "co_owner_id": str(user_id),
        "merged": bool(req.merge_pet_id),
    })

    return {"status": "shared", "pet_id": str(share_token.pet_id)}


@router.post("/{pet_id}/unshare")
async def unshare_pet(
    pet_id: str,
    req: UnshareRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Co-owner leaves a shared pet. Optionally keep a copy."""
    pid = uuid.UUID(pet_id)

    # Verify co-owner
    co_q = await db.execute(
        select(PetCoOwner).where(
            PetCoOwner.pet_id == pid,
            PetCoOwner.user_id == user_id,
        )
    )
    co_owner = co_q.scalar_one_or_none()
    if not co_owner:
        raise HTTPException(404, detail="Not a co-owner of this pet")

    if req.keep_copy:
        await _deep_copy_pet(db, pid, user_id)

    # Remove co-ownership
    await db.delete(co_owner)
    await db.commit()

    logger.info("pet_unshared", extra={
        "pet_id": pet_id,
        "user_id": str(user_id),
        "kept_copy": req.keep_copy,
    })

    return {"status": "unshared", "kept_copy": req.keep_copy}


async def _merge_pets(
    db: AsyncSession,
    target_pet_id: uuid.UUID,
    source_pet_id: uuid.UUID,
    source_user_id: uuid.UUID,
):
    """Merge source pet (B's) into target pet (A's). Moves events/reminders, deletes source."""
    # Verify source pet belongs to the user
    source_q = await db.execute(
        select(Pet).where(Pet.id == source_pet_id, Pet.user_id == source_user_id)
    )
    source_pet = source_q.scalar_one_or_none()
    if not source_pet:
        return  # Nothing to merge

    target_q = await db.execute(select(Pet).where(Pet.id == target_pet_id))
    target_pet = target_q.scalar_one_or_none()
    if not target_pet:
        return

    # Move calendar events from source to target, mark created_by
    await db.execute(
        update(CalendarEvent)
        .where(CalendarEvent.pet_id == source_pet_id)
        .values(pet_id=target_pet_id, created_by=source_user_id)
    )

    # Move reminders from source to target, mark created_by
    await db.execute(
        update(Reminder)
        .where(Reminder.pet_id == source_pet_id)
        .values(pet_id=target_pet_id, created_by=source_user_id)
    )

    # TODO: LLM merge of profile_md (implement in Task 6)

    # Delete source pet
    await db.delete(source_pet)

    logger.info("pet_merged", extra={
        "target": str(target_pet_id),
        "source": str(source_pet_id),
        "events_moved": True,
    })


async def _deep_copy_pet(
    db: AsyncSession, pet_id: uuid.UUID, user_id: uuid.UUID
):
    """Deep copy a pet and its data for the leaving co-owner."""
    pet_q = await db.execute(select(Pet).where(Pet.id == pet_id))
    original = pet_q.scalar_one_or_none()
    if not original:
        return

    # Create new pet for user
    new_pet = Pet(
        user_id=user_id,
        name=original.name,
        species=original.species,
        species_locked=original.species_locked,
        breed=original.breed,
        birthday=original.birthday,
        weight=original.weight,
        avatar_url=original.avatar_url,
        color_hex=original.color_hex,
        profile=original.profile,
        profile_md=original.profile_md,
    )
    db.add(new_pet)
    await db.flush()  # Get new_pet.id

    # Copy events
    events_q = await db.execute(
        select(CalendarEvent).where(CalendarEvent.pet_id == pet_id)
    )
    for event in events_q.scalars():
        new_event = CalendarEvent(
            user_id=user_id,
            pet_id=new_pet.id,
            title=event.title,
            category=event.category,
            event_date=event.event_date,
            notes=event.notes,
            raw_text=event.raw_text,
            source=event.source,
            cost=event.cost,
            created_by=event.created_by,
        )
        db.add(new_event)

    # Copy reminders
    reminders_q = await db.execute(
        select(Reminder).where(Reminder.pet_id == pet_id)
    )
    for rem in reminders_q.scalars():
        new_rem = Reminder(
            user_id=user_id,
            pet_id=new_pet.id,
            title=rem.title,
            body=rem.body,
            trigger_at=rem.trigger_at,
            created_by=rem.created_by,
        )
        db.add(new_rem)

    logger.info("pet_deep_copied", extra={
        "original_id": str(pet_id),
        "copy_id": str(new_pet.id),
        "user_id": str(user_id),
    })


# Register router in main.py
```

- [ ] **Step 2: Register in main.py**

In `backend/app/main.py`:
```python
from app.routers.pet_sharing import router as pet_sharing_router
app.include_router(pet_sharing_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/pet_sharing.py backend/app/main.py
git commit -m "feat: add pet sharing endpoints (share-token, accept, unshare, merge, copy)"
```

---

### Task 6: LLM Profile Merge

**Files:**
- Create: `backend/app/agents/tools/profile_merge.py`
- Modify: `backend/app/routers/pet_sharing.py` — call profile merge in `_merge_pets`

- [ ] **Step 1: Create profile merge function**

```python
"""Merge two pet profile_md documents using LLM."""

import logging
import litellm
from app.agents import llm_extra_kwargs
from app.config import settings

logger = logging.getLogger(__name__)


async def merge_pet_profiles(profile_a: str | None, profile_b: str | None) -> str | None:
    """Use LLM to merge two pet profile documents. Returns merged markdown."""
    if not profile_a and not profile_b:
        return None
    if not profile_a:
        return profile_b
    if not profile_b:
        return profile_a

    prompt = f"""Merge these two pet profile documents into one cohesive document.
Keep all unique information from both profiles.
When information conflicts, prefer Profile A (the primary owner's version).
Output a single markdown document, under 500 words.

## Profile A (primary):
{profile_a}

## Profile B (secondary):
{profile_b}

Output ONLY the merged profile document, no explanation."""

    try:
        response = await litellm.acompletion(
            model=settings.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1000,
            **llm_extra_kwargs(),
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("profile_merge_error", extra={"error": str(exc)[:200]})
        # Fallback: just concat
        return f"{profile_a}\n\n---\n\n{profile_b}"
```

- [ ] **Step 2: Wire into _merge_pets**

In `backend/app/routers/pet_sharing.py`, replace the `# TODO: LLM merge` line:

```python
from app.agents.tools.profile_merge import merge_pet_profiles

# In _merge_pets, replace the TODO line with:
if source_pet.profile_md or target_pet.profile_md:
    target_pet.profile_md = await merge_pet_profiles(
        target_pet.profile_md, source_pet.profile_md
    )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/agents/tools/profile_merge.py backend/app/routers/pet_sharing.py
git commit -m "feat: add LLM-powered pet profile merge"
```

---

### Task 7: iOS — QR Code Share Screen

**Files:**
- Create: `ios-app/CozyPup/Views/Pets/PetShareSheet.swift`

- [ ] **Step 1: Create QR share sheet**

```swift
import SwiftUI
import CoreImage.CIFilterBuiltins

struct PetShareSheet: View {
    let petId: String
    let petName: String
    @State private var token: String?
    @State private var expiresAt: Date?
    @State private var isLoading = true

    var body: some View {
        VStack(spacing: Tokens.spacing.lg) {
            RoundedRectangle(cornerRadius: 2)
                .fill(Tokens.border)
                .frame(width: 36, height: 4)
                .padding(.top, Tokens.spacing.sm)

            Text("Share \(petName)")
                .font(Tokens.fontTitle)
                .foregroundColor(Tokens.text)

            Text("Let someone scan to co-own this pet")
                .font(Tokens.fontSubheadline)
                .foregroundColor(Tokens.textSecondary)

            if isLoading {
                ProgressView()
                    .frame(width: 200, height: 200)
            } else if let token {
                let url = "cozypup://share?token=\(token)"
                if let image = generateQRCode(from: url) {
                    Image(uiImage: image)
                        .interpolation(.none)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 200, height: 200)
                        .cornerRadius(Tokens.radiusSmall)
                }

                if let expiresAt {
                    Text("Expires \(expiresAt, style: .relative)")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)
                }
            }

            Spacer()
        }
        .padding(Tokens.spacing.md)
        .task { await generateToken() }
    }

    private func generateToken() async {
        struct Resp: Decodable {
            let token: String
            let expires_at: String
        }
        do {
            let resp: Resp = try await APIClient.shared.request(
                "POST", "/pets/\(petId)/share-token"
            )
            token = resp.token
            let formatter = ISO8601DateFormatter()
            expiresAt = formatter.date(from: resp.expires_at)
            isLoading = false
        } catch {
            print("[PetShare] Failed to generate token: \(error)")
            isLoading = false
        }
    }

    private func generateQRCode(from string: String) -> UIImage? {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(string.utf8)
        filter.correctionLevel = "M"

        guard let output = filter.outputImage else { return nil }
        let scaled = output.transformed(by: CGAffineTransform(scaleX: 10, y: 10))
        let context = CIContext()
        guard let cgImage = context.createCGImage(scaled, from: scaled.extent) else { return nil }
        return UIImage(cgImage: cgImage)
    }
}

#Preview {
    PetShareSheet(petId: "test-id", petName: "Weini")
}
```

- [ ] **Step 2: Commit**

```bash
git add -f ios-app/CozyPup/Views/Pets/PetShareSheet.swift
git commit -m "feat: add QR code pet sharing screen"
```

---

### Task 8: iOS — Scan & Merge Screen

**Files:**
- Create: `ios-app/CozyPup/Views/Pets/PetMergeSheet.swift`

- [ ] **Step 1: Create merge selection sheet**

```swift
import SwiftUI

struct PetMergeSheet: View {
    let shareToken: String
    @EnvironmentObject var petStore: PetStore
    @State private var selectedPetId: String?
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    var onDone: (() -> Void)?

    var body: some View {
        VStack(spacing: Tokens.spacing.lg) {
            RoundedRectangle(cornerRadius: 2)
                .fill(Tokens.border)
                .frame(width: 36, height: 4)
                .padding(.top, Tokens.spacing.sm)

            Text("Merge with your pet?")
                .font(Tokens.fontTitle)
                .foregroundColor(Tokens.text)

            if petStore.pets.isEmpty {
                Text("You don't have any pets yet. The shared pet will be added to your list.")
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.textSecondary)
                    .multilineTextAlignment(.center)
                    .padding()
            } else {
                ScrollView {
                    VStack(spacing: Tokens.spacing.sm) {
                        ForEach(petStore.pets, id: \.id) { pet in
                            Button {
                                selectedPetId = selectedPetId == pet.id ? nil : pet.id
                            } label: {
                                HStack(spacing: Tokens.spacing.sm) {
                                    // Avatar
                                    if let url = pet.avatarUrl, !url.isEmpty {
                                        AsyncImage(url: URL(string: url)) { image in
                                            image.resizable().scaledToFill()
                                        } placeholder: {
                                            Color(hex: pet.colorHex)
                                        }
                                        .frame(width: 40, height: 40)
                                        .cornerRadius(10)
                                    } else {
                                        RoundedRectangle(cornerRadius: 10)
                                            .fill(Color(hex: pet.colorHex))
                                            .frame(width: 40, height: 40)
                                    }

                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(pet.name)
                                            .font(Tokens.fontBody.weight(.semibold))
                                            .foregroundColor(Tokens.text)
                                        Text(pet.breed)
                                            .font(Tokens.fontCaption)
                                            .foregroundColor(Tokens.textSecondary)
                                    }

                                    Spacer()

                                    Circle()
                                        .strokeBorder(
                                            selectedPetId == pet.id ? Tokens.accent : Tokens.border,
                                            lineWidth: 1.5
                                        )
                                        .background(
                                            Circle().fill(
                                                selectedPetId == pet.id ? Tokens.accent : Color.clear
                                            )
                                        )
                                        .overlay(
                                            selectedPetId == pet.id
                                                ? Image(systemName: "checkmark")
                                                    .font(.system(size: 10, weight: .bold))
                                                    .foregroundColor(Tokens.white)
                                                : nil
                                        )
                                        .frame(width: 22, height: 22)
                                }
                                .padding(Tokens.spacing.sm)
                                .background(
                                    selectedPetId == pet.id ? Tokens.accentSoft : Tokens.surface
                                )
                                .cornerRadius(Tokens.radiusSmall)
                                .overlay(
                                    RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                                        .stroke(
                                            selectedPetId == pet.id ? Tokens.accent : Tokens.border,
                                            lineWidth: 1.5
                                        )
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.red)
            }

            Button {
                Task { await acceptShare() }
            } label: {
                if isSubmitting {
                    ProgressView().tint(Tokens.white)
                } else {
                    Text(selectedPetId != nil ? "Confirm Merge" : "Add Without Merging")
                }
            }
            .font(Tokens.fontBody.weight(.semibold))
            .foregroundColor(Tokens.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(Tokens.accent)
            .cornerRadius(Tokens.radiusSmall)
            .disabled(isSubmitting)

            if selectedPetId != nil {
                Button {
                    selectedPetId = nil
                } label: {
                    Text("Skip — add without merging")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)
                }
            }

            Spacer()
        }
        .padding(Tokens.spacing.md)
    }

    private func acceptShare() async {
        isSubmitting = true
        defer { isSubmitting = false }

        struct Body: Encodable {
            let token: String
            let merge_pet_id: String?
        }
        struct Resp: Decodable {
            let status: String
            let pet_id: String
        }

        do {
            let _: Resp = try await APIClient.shared.request(
                "POST", "/pets/accept-share",
                body: Body(token: shareToken, merge_pet_id: selectedPetId)
            )
            await petStore.fetchFromAPI()
            onDone?()
        } catch {
            errorMessage = "Failed to accept share: \(error.localizedDescription)"
        }
    }
}

#Preview {
    PetMergeSheet(shareToken: "test-token")
        .environmentObject(PetStore())
}
```

- [ ] **Step 2: Commit**

```bash
git add -f ios-app/CozyPup/Views/Pets/PetMergeSheet.swift
git commit -m "feat: add pet merge selection screen for QR sharing"
```

---

### Task 9: iOS — Deep Link Handling & QR Scanner

**Files:**
- Modify: `ios-app/CozyPup/CozyPupApp.swift` — handle `cozypup://share?token=` deep links
- Add QR scanner using iOS camera (AVFoundation or native Code Scanner)

- [ ] **Step 1: Add deep link handler in CozyPupApp**

In `CozyPupApp.swift`, add `.onOpenURL` handler:

```swift
.onOpenURL { url in
    if url.scheme == "cozypup" && url.host == "share",
       let token = URLComponents(url: url, resolvingAgainstBaseURL: false)?
           .queryItems?.first(where: { $0.name == "token" })?.value {
        // Present PetMergeSheet with this token
        pendingShareToken = token
        showMergeSheet = true
    }
}
```

Add `@State` vars for `pendingShareToken` and `showMergeSheet`, and a `.sheet` modifier for PetMergeSheet.

- [ ] **Step 2: Commit**

```bash
git add -f ios-app/CozyPup/CozyPupApp.swift
git commit -m "feat: handle cozypup://share deep links for pet sharing"
```

---

### Task 10: iOS — Unshare UI

**Files:**
- Create: `ios-app/CozyPup/Views/Pets/PetUnshareSheet.swift`

- [ ] **Step 1: Create unshare sheet with two options**

```swift
import SwiftUI

struct PetUnshareSheet: View {
    let petId: String
    let petName: String
    @State private var isSubmitting = false
    var onDone: (() -> Void)?

    var body: some View {
        VStack(spacing: Tokens.spacing.lg) {
            RoundedRectangle(cornerRadius: 2)
                .fill(Tokens.border)
                .frame(width: 36, height: 4)
                .padding(.top, Tokens.spacing.sm)

            Text("Leave \(petName)?")
                .font(Tokens.fontTitle)
                .foregroundColor(Tokens.text)

            HStack(spacing: Tokens.spacing.md) {
                // Keep copy
                Button {
                    Task { await unshare(keepCopy: true) }
                } label: {
                    VStack(spacing: Tokens.spacing.sm) {
                        Text("📋").font(.title)
                        Text("Keep a copy")
                            .font(Tokens.fontSubheadline.weight(.semibold))
                            .foregroundColor(Tokens.text)
                        Text("All data is copied. No longer synced.")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(Tokens.spacing.md)
                    .background(Tokens.surface)
                    .cornerRadius(Tokens.radiusSmall)
                    .overlay(
                        RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                            .stroke(Tokens.border, lineWidth: 1.5)
                    )
                }
                .buttonStyle(.plain)

                // Just leave
                Button {
                    Task { await unshare(keepCopy: false) }
                } label: {
                    VStack(spacing: Tokens.spacing.sm) {
                        Text("👋").font(.title)
                        Text("Just leave")
                            .font(Tokens.fontSubheadline.weight(.semibold))
                            .foregroundColor(Tokens.text)
                        Text("Pet disappears. Data stays with owner.")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(Tokens.spacing.md)
                    .background(Tokens.surface)
                    .cornerRadius(Tokens.radiusSmall)
                    .overlay(
                        RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                            .stroke(Tokens.border, lineWidth: 1.5)
                    )
                }
                .buttonStyle(.plain)
            }

            if isSubmitting {
                ProgressView()
            }

            Spacer()
        }
        .padding(Tokens.spacing.md)
    }

    private func unshare(keepCopy: Bool) async {
        isSubmitting = true
        struct Body: Encodable { let keep_copy: Bool }
        struct Resp: Decodable { let status: String }
        do {
            let _: Resp = try await APIClient.shared.request(
                "POST", "/pets/\(petId)/unshare",
                body: Body(keep_copy: keepCopy)
            )
            onDone?()
        } catch {
            print("[Unshare] failed: \(error)")
        }
        isSubmitting = false
    }
}

#Preview {
    PetUnshareSheet(petId: "test", petName: "Weini")
}
```

- [ ] **Step 2: Commit**

```bash
git add -f ios-app/CozyPup/Views/Pets/PetUnshareSheet.swift
git commit -m "feat: add pet unshare screen with keep-copy and leave options"
```
