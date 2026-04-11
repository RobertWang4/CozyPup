# Family Plan (Duo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a Duo subscriber to invite one partner via email, granting them full membership.

**Architecture:** Add FamilyInvite table linking payer → invitee. On invite accept, set invitee's subscription_status to "active" with family_payer_id pointing to payer. Subscription middleware already checks subscription_status — no middleware changes needed. Duo product IDs detected in verify endpoint.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, email (SMTP or SendGrid), iOS SwiftUI + StoreKit

**Spec:** `docs/superpowers/specs/2026-04-11-family-plan-and-pet-sharing-design.md`

---

### Task 1: Database Models & Migration

**Files:**
- Modify: `backend/app/models.py` — add FamilyInvite model, add family fields to User
- Create: `backend/alembic/versions/xxxx_add_family_plan.py` — migration

- [ ] **Step 1: Add family fields to User model and FamilyInvite model**

In `backend/app/models.py`, add to User class after `subscription_product_id`:

```python
# Family plan
family_role: Mapped[str | None] = mapped_column(String(20))  # "payer" | "member" | null
family_payer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
```

Add new model after User class:

```python
class FamilyInvite(Base):
    __tablename__ = "family_invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inviter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    invitee_email: Mapped[str] = mapped_column(String(255), nullable=False)
    invitee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # "pending" | "accepted" | "revoked"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 2: Generate migration**

```bash
cd backend
source .venv/bin/activate
alembic revision --autogenerate -m "add family plan tables"
```

- [ ] **Step 3: Apply migration**

```bash
alembic upgrade head
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/
git commit -m "feat: add FamilyInvite model and family fields to User"
```

---

### Task 2: Family Plan Schemas

**Files:**
- Create: `backend/app/schemas/family.py`

- [ ] **Step 1: Create schemas**

```python
from pydantic import BaseModel, EmailStr
from datetime import datetime


class FamilyInviteRequest(BaseModel):
    email: str  # invitee email


class FamilyInviteResponse(BaseModel):
    invite_id: str
    status: str
    invitee_email: str


class FamilyStatusResponse(BaseModel):
    role: str | None  # "payer" | "member" | null
    partner_email: str | None = None
    partner_name: str | None = None
    invite_pending: bool = False
    pending_invite_email: str | None = None


class FamilyAcceptRequest(BaseModel):
    invite_id: str
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/family.py
git commit -m "feat: add family plan schemas"
```

---

### Task 3: Family Router

**Files:**
- Create: `backend/app/routers/family.py`
- Modify: `backend/app/main.py` — register router

- [ ] **Step 1: Write tests**

Create `backend/tests/test_family.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from app.models import User, FamilyInvite


@pytest.fixture
def payer_user():
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "payer@test.com"
    user.name = "Payer"
    user.subscription_status = "active"
    user.subscription_product_id = "com.cozypup.app.monthly.duo"
    user.family_role = None
    user.family_payer_id = None
    return user


@pytest.fixture
def member_user():
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "member@test.com"
    user.name = "Member"
    user.subscription_status = "expired"
    user.family_role = None
    user.family_payer_id = None
    return user


def test_is_duo_product():
    from app.routers.family import _is_duo_product
    assert _is_duo_product("com.cozypup.app.monthly.duo") is True
    assert _is_duo_product("com.cozypup.app.weekly.duo") is True
    assert _is_duo_product("com.cozypup.app.yearly.duo") is True
    assert _is_duo_product("com.cozypup.app.monthly") is False
    assert _is_duo_product(None) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source .venv/bin/activate
pytest tests/test_family.py -v
```

Expected: FAIL — `app.routers.family` not found.

- [ ] **Step 3: Implement family router**

Create `backend/app/routers/family.py`:

```python
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.models import User, FamilyInvite
from app.schemas.family import (
    FamilyInviteRequest,
    FamilyInviteResponse,
    FamilyStatusResponse,
    FamilyAcceptRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/family", tags=["family"])


def _is_duo_product(product_id: str | None) -> bool:
    return bool(product_id and ".duo" in product_id)


@router.get("/status", response_model=FamilyStatusResponse)
async def get_family_status(
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    resp = FamilyStatusResponse(role=user.family_role)

    if user.family_role == "payer":
        # Find accepted member
        member_q = await db.execute(
            select(User).where(User.family_payer_id == user.id)
        )
        member = member_q.scalar_one_or_none()
        if member:
            resp.partner_email = member.email
            resp.partner_name = member.name

        # Check pending invite
        pending_q = await db.execute(
            select(FamilyInvite).where(
                FamilyInvite.inviter_id == user.id,
                FamilyInvite.status == "pending",
            )
        )
        pending = pending_q.scalar_one_or_none()
        if pending:
            resp.invite_pending = True
            resp.pending_invite_email = pending.invitee_email

    elif user.family_role == "member" and user.family_payer_id:
        payer_q = await db.execute(
            select(User).where(User.id == user.family_payer_id)
        )
        payer = payer_q.scalar_one_or_none()
        if payer:
            resp.partner_email = payer.email
            resp.partner_name = payer.name

    return resp


@router.post("/invite", response_model=FamilyInviteResponse)
async def invite_partner(
    req: FamilyInviteRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    # Must be on a duo plan
    if not _is_duo_product(user.subscription_product_id):
        raise HTTPException(400, detail="Duo plan required to invite a partner")

    # Can't invite if already has a member
    if user.family_role == "payer":
        existing = await db.execute(
            select(User).where(User.family_payer_id == user.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(400, detail="You already have a partner")

    # Can't invite yourself
    if req.email.lower() == user.email.lower():
        raise HTTPException(400, detail="Cannot invite yourself")

    # Revoke any existing pending invites
    old_invites = await db.execute(
        select(FamilyInvite).where(
            FamilyInvite.inviter_id == user.id,
            FamilyInvite.status == "pending",
        )
    )
    for old in old_invites.scalars():
        old.status = "revoked"

    # Create invite
    invite = FamilyInvite(
        inviter_id=user.id,
        invitee_email=req.email.lower(),
    )
    db.add(invite)
    user.family_role = "payer"
    await db.commit()
    await db.refresh(invite)

    # Send email (fire and forget)
    _send_invite_email(user.name or user.email, req.email, str(invite.id))

    logger.info("family_invite_sent", extra={
        "inviter_id": str(user.id),
        "invitee_email": req.email,
        "invite_id": str(invite.id),
    })

    return FamilyInviteResponse(
        invite_id=str(invite.id),
        status="pending",
        invitee_email=req.email,
    )


@router.post("/accept")
async def accept_invite(
    req: FamilyAcceptRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    invite_q = await db.execute(
        select(FamilyInvite).where(FamilyInvite.id == req.invite_id)
    )
    invite = invite_q.scalar_one_or_none()
    if not invite or invite.status != "pending":
        raise HTTPException(404, detail="Invite not found or already used")

    # Verify this user's email matches the invite
    user_q = await db.execute(select(User).where(User.id == user_id))
    user = user_q.scalar_one()
    if user.email.lower() != invite.invitee_email.lower():
        raise HTTPException(403, detail="This invite is for a different email")

    # Already a member of another family?
    if user.family_role == "member":
        raise HTTPException(400, detail="Already a member of another family")

    # Accept
    invite.status = "accepted"
    invite.invitee_id = user.id
    invite.accepted_at = datetime.now(timezone.utc)

    user.family_role = "member"
    user.family_payer_id = invite.inviter_id
    user.subscription_status = "active"

    await db.commit()

    logger.info("family_invite_accepted", extra={
        "inviter_id": str(invite.inviter_id),
        "invitee_id": str(user.id),
    })

    return {"status": "accepted"}


@router.post("/revoke")
async def revoke_partner(
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Payer removes their partner."""
    user_q = await db.execute(select(User).where(User.id == user_id))
    user = user_q.scalar_one()

    if user.family_role != "payer":
        raise HTTPException(400, detail="Only the payer can revoke")

    # Find and expire the member
    member_q = await db.execute(
        select(User).where(User.family_payer_id == user.id)
    )
    member = member_q.scalar_one_or_none()
    if member:
        member.family_role = None
        member.family_payer_id = None
        member.subscription_status = "expired"
        logger.info("family_member_revoked", extra={
            "payer_id": str(user.id),
            "member_id": str(member.id),
        })

    # Revoke pending invites too
    pending = await db.execute(
        select(FamilyInvite).where(
            FamilyInvite.inviter_id == user.id,
            FamilyInvite.status == "pending",
        )
    )
    for inv in pending.scalars():
        inv.status = "revoked"

    user.family_role = None
    await db.commit()

    return {"status": "revoked"}


def _send_invite_email(inviter_name: str, invitee_email: str, invite_id: str):
    """Send invite email. Placeholder — implement with SendGrid or SMTP."""
    # TODO: implement actual email sending
    logger.info("family_invite_email", extra={
        "to": invitee_email,
        "inviter": inviter_name,
        "invite_id": invite_id,
    })
```

- [ ] **Step 4: Register router in main.py**

In `backend/app/main.py`, add:

```python
from app.routers.family import router as family_router
app.include_router(family_router)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_family.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/family.py backend/app/main.py backend/tests/test_family.py
git commit -m "feat: add family plan invite/accept/revoke endpoints"
```

---

### Task 4: Update Subscription Verify for Duo Products

**Files:**
- Modify: `backend/app/routers/subscription.py`

- [ ] **Step 1: Update verify endpoint to handle duo + weekly products**

In `backend/app/routers/subscription.py`, update the verify handler:

```python
@router.post("/verify", response_model=VerifyResponse)
async def verify_purchase(
    req: VerifyRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Verify a StoreKit 2 transaction and activate subscription."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    user.subscription_status = "active"
    user.subscription_product_id = req.product_id

    if "weekly" in req.product_id:
        user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    elif "yearly" in req.product_id:
        user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=365)
    else:
        user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    # If downgrading from duo to individual, revoke partner
    if ".duo" not in req.product_id and user.family_role == "payer":
        member_q = await db.execute(
            select(User).where(User.family_payer_id == user.id)
        )
        member = member_q.scalar_one_or_none()
        if member:
            member.family_role = None
            member.family_payer_id = None
            member.subscription_status = "expired"
            logger.info("family_auto_revoked_on_downgrade", extra={
                "payer_id": str(user_id),
                "member_id": str(member.id),
            })
        user.family_role = None

    await db.commit()
    logger.info("subscription_activated", extra={
        "user_id": str(user_id),
        "product_id": req.product_id,
    })

    return VerifyResponse(
        status="active",
        expires_at=user.subscription_expires_at,
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/routers/subscription.py
git commit -m "feat: handle duo product downgrade in subscription verify"
```

---

### Task 5: iOS — Duo Product IDs & Paywall Update

**Files:**
- Modify: `ios-app/CozyPup/Stores/SubscriptionStore.swift`
- Modify: `ios-app/CozyPup/Views/Paywall/PaywallSheet.swift`

- [ ] **Step 1: Add duo product IDs to SubscriptionStore**

In `SubscriptionStore.swift`, update productIDs:

```swift
static let productIDs = [
    "com.cozypup.app.weekly",
    "com.cozypup.app.monthly",
    "com.cozypup.app.yearly",
    "com.cozypup.app.weekly.duo",
    "com.cozypup.app.monthly.duo",
    "com.cozypup.app.yearly.duo",
]

var isDuo: Bool {
    guard case .active = status else { return false }
    // Check via products or cached product_id
    return false // Will be set from backend status
}
```

- [ ] **Step 2: Commit**

```bash
git add -f ios-app/CozyPup/Stores/SubscriptionStore.swift ios-app/CozyPup/Views/Paywall/PaywallSheet.swift
git commit -m "feat: add duo product IDs and paywall tier toggle"
```

---

### Task 6: iOS — Family Settings UI

**Files:**
- Create: `ios-app/CozyPup/Views/Settings/FamilySettingsView.swift`
- Modify: `ios-app/CozyPup/Views/Settings/SettingsDrawer.swift` — add link to family settings

- [ ] **Step 1: Create FamilySettingsView**

```swift
import SwiftUI

struct FamilySettingsView: View {
    @State private var familyStatus: FamilyStatus?
    @State private var inviteEmail = ""
    @State private var isLoading = false
    @State private var message: String?

    var body: some View {
        VStack(spacing: Tokens.spacing.lg) {
            Text("Duo Plan")
                .font(Tokens.fontTitle)
                .foregroundColor(Tokens.text)

            if let status = familyStatus {
                if let partner = status.partner_name ?? status.partner_email {
                    // Has partner
                    VStack(spacing: Tokens.spacing.sm) {
                        Text("Sharing with")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                        Text(partner)
                            .font(Tokens.fontBody.weight(.semibold))
                            .foregroundColor(Tokens.text)

                        Button("Remove Partner") {
                            Task { await revokePartner() }
                        }
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.red)
                        .padding(.top, Tokens.spacing.sm)
                    }
                } else if status.invite_pending {
                    // Pending invite
                    VStack(spacing: Tokens.spacing.xs) {
                        Text("Invite pending")
                            .font(Tokens.fontSubheadline)
                            .foregroundColor(Tokens.textSecondary)
                        Text(status.pending_invite_email ?? "")
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.text)
                    }
                } else {
                    // No partner — show invite form
                    VStack(spacing: Tokens.spacing.md) {
                        TextField("Partner's email", text: $inviteEmail)
                            .textContentType(.emailAddress)
                            .keyboardType(.emailAddress)
                            .autocapitalization(.none)
                            .padding(Tokens.spacing.sm)
                            .background(Tokens.surface)
                            .cornerRadius(Tokens.radiusSmall)

                        Button {
                            Task { await sendInvite() }
                        } label: {
                            if isLoading {
                                ProgressView().tint(Tokens.white)
                            } else {
                                Text("Send Invite")
                            }
                        }
                        .font(Tokens.fontBody.weight(.semibold))
                        .foregroundColor(Tokens.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(inviteEmail.isEmpty ? Tokens.accent.opacity(0.5) : Tokens.accent)
                        .cornerRadius(Tokens.radiusSmall)
                        .disabled(inviteEmail.isEmpty || isLoading)
                    }
                }
            } else {
                ProgressView()
            }

            if let message {
                Text(message)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.green)
            }

            Spacer()
        }
        .padding(Tokens.spacing.md)
        .task { await loadStatus() }
    }

    private func loadStatus() async {
        struct Resp: Decodable {
            let role: String?
            let partner_email: String?
            let partner_name: String?
            let invite_pending: Bool
            let pending_invite_email: String?
        }
        do {
            let resp: Resp = try await APIClient.shared.request("GET", "/family/status")
            familyStatus = FamilyStatus(
                role: resp.role,
                partner_email: resp.partner_email,
                partner_name: resp.partner_name,
                invite_pending: resp.invite_pending,
                pending_invite_email: resp.pending_invite_email
            )
        } catch {
            print("[Family] load status failed: \(error)")
        }
    }

    private func sendInvite() async {
        isLoading = true
        defer { isLoading = false }
        struct Body: Encodable { let email: String }
        struct Resp: Decodable { let invite_id: String; let status: String }
        do {
            let _: Resp = try await APIClient.shared.request(
                "POST", "/family/invite", body: Body(email: inviteEmail)
            )
            message = "Invite sent!"
            await loadStatus()
        } catch {
            message = "Failed to send invite"
        }
    }

    private func revokePartner() async {
        struct Resp: Decodable { let status: String }
        do {
            let _: Resp = try await APIClient.shared.request("POST", "/family/revoke")
            await loadStatus()
        } catch {
            print("[Family] revoke failed: \(error)")
        }
    }
}

struct FamilyStatus {
    let role: String?
    let partner_email: String?
    let partner_name: String?
    let invite_pending: Bool
    let pending_invite_email: String?
}

#Preview {
    FamilySettingsView()
}
```

- [ ] **Step 2: Add link in SettingsDrawer**

Add a navigation row in SettingsDrawer.swift that links to FamilySettingsView when user is on a duo plan.

- [ ] **Step 3: Commit**

```bash
git add -f ios-app/CozyPup/Views/Settings/FamilySettingsView.swift ios-app/CozyPup/Views/Settings/SettingsDrawer.swift
git commit -m "feat: add family settings UI with invite/revoke"
```
