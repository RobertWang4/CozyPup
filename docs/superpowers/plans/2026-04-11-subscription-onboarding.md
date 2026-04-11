# Subscription & Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add subscription billing (StoreKit 2 + backend), paywall UI, and new-user onboarding (welcome message + quick-action cards + placeholder rotation).

**Architecture:** Backend adds subscription fields to User model, a new `/subscription` router for status/stats/verify/webhook, and a middleware dependency to block writes for expired users. iOS adds `SubscriptionStore` (StoreKit 2), `PaywallSheet`, quick-action cards in `ChatView`, and placeholder rotation in `ChatInputBar`.

**Tech Stack:** StoreKit 2 (iOS 17+), App Store Server Notifications V2, FastAPI, SQLAlchemy, Alembic

**Spec:** `docs/superpowers/specs/2026-04-11-subscription-onboarding-design.md`

---

## File Map

### Backend — New Files
| File | Purpose |
|------|---------|
| `backend/app/routers/subscription.py` | Subscription API: status, trial-stats, verify, webhook |
| `backend/app/schemas/subscription.py` | Pydantic models for subscription endpoints |
| `backend/app/middleware/subscription.py` | Dependency that blocks writes for expired users |
| `backend/tests/test_subscription.py` | Tests for subscription router + middleware |

### Backend — Modified Files
| File | Change |
|------|--------|
| `backend/app/models.py:64-78` | Add subscription fields to User model |
| `backend/app/main.py:9-53` | Register subscription router + middleware |
| `backend/app/routers/auth.py:37-57` | Set `subscription_status="trial"` + `trial_start_date` on user creation |

### iOS — New Files
| File | Purpose |
|------|---------|
| `ios-app/CozyPup/Stores/SubscriptionStore.swift` | StoreKit 2 product loading, purchase, status monitoring |
| `ios-app/CozyPup/Views/Paywall/PaywallSheet.swift` | Soft + hard paywall sheet (shared component) |
| `ios-app/CozyPup/Views/Chat/QuickActionCards.swift` | 2x2 quick-action card grid |

### iOS — Modified Files
| File | Change |
|------|--------|
| `ios-app/CozyPup/CozyPupApp.swift:59-98` | Add `SubscriptionStore` as environment object |
| `ios-app/CozyPup/Views/Chat/ChatView.swift:63-82` | Replace `EmptyStateView` with quick-action cards + welcome message |
| `ios-app/CozyPup/Views/Chat/ChatInputBar.swift` | Add placeholder rotation |
| `ios-app/CozyPup/Stores/ChatStore.swift` | Add `messageCount` tracking for soft paywall trigger |
| `ios-app/CozyPup/Views/Settings/SettingsDrawer.swift` | Add subscription status + renew button |

---

## Task 1: Backend — Add subscription fields to User model

**Files:**
- Modify: `backend/app/models.py:64-78`
- Create: Alembic migration (auto-generated)

- [ ] **Step 1: Add subscription fields to User model**

In `backend/app/models.py`, add these fields to the `User` class after `updated_at` (line 74):

```python
    subscription_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="trial")  # "trial" | "active" | "expired"
    trial_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_product_id: Mapped[str | None] = mapped_column(String(100))
```

- [ ] **Step 2: Generate Alembic migration**

```bash
cd backend
source .venv/bin/activate
alembic revision --autogenerate -m "add subscription fields to user"
```

Expected: Migration file created in `backend/alembic/versions/`

- [ ] **Step 3: Apply migration**

```bash
alembic upgrade head
```

Expected: Migration applied successfully, no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/
git commit -m "feat: add subscription fields to User model"
```

---

## Task 2: Backend — Subscription schemas

**Files:**
- Create: `backend/app/schemas/subscription.py`

- [ ] **Step 1: Create subscription schemas**

```python
from pydantic import BaseModel
from datetime import datetime


class SubscriptionStatusResponse(BaseModel):
    status: str  # "trial" | "active" | "expired"
    trial_days_left: int | None = None
    expires_at: datetime | None = None


class TrialStatsResponse(BaseModel):
    chat_count: int
    reminder_count: int
    event_count: int


class VerifyRequest(BaseModel):
    transaction_id: str
    product_id: str


class VerifyResponse(BaseModel):
    status: str
    expires_at: datetime | None = None
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/subscription.py
git commit -m "feat: add subscription Pydantic schemas"
```

---

## Task 3: Backend — Subscription router

**Files:**
- Create: `backend/app/routers/subscription.py`
- Create: `backend/tests/test_subscription.py`

- [ ] **Step 1: Write tests for subscription endpoints**

Create `backend/tests/test_subscription.py`:

```python
import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

from app.main import app
from app.models import User
from app.auth import create_access_token


@pytest.fixture
def auth_headers():
    """Create auth headers for a test user."""
    token = create_access_token("00000000-0000-0000-0000-000000000001")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def trial_user(async_session):
    """Create a user in trial status."""
    user = User(
        id="00000000-0000-0000-0000-000000000001",
        email="test@example.com",
        name="Test",
        auth_provider="dev",
        subscription_status="trial",
        trial_start_date=datetime.now(timezone.utc),
    )
    async_session.add(user)
    await async_session.commit()
    return user


@pytest.fixture
async def expired_user(async_session):
    """Create a user with expired trial."""
    user = User(
        id="00000000-0000-0000-0000-000000000001",
        email="test@example.com",
        name="Test",
        auth_provider="dev",
        subscription_status="trial",
        trial_start_date=datetime.now(timezone.utc) - timedelta(days=8),
    )
    async_session.add(user)
    await async_session.commit()
    return user


@pytest.mark.asyncio
async def test_subscription_status_trial(trial_user, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/subscription/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "trial"
    assert data["trial_days_left"] >= 6  # just created, ~7 days left


@pytest.mark.asyncio
async def test_subscription_status_expired(expired_user, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/subscription/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "expired"
    assert data["trial_days_left"] == 0


@pytest.mark.asyncio
async def test_trial_stats(trial_user, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/subscription/trial-stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "chat_count" in data
    assert "reminder_count" in data
    assert "event_count" in data
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_subscription.py -v
```

Expected: FAIL — `ModuleNotFoundError` or import errors (router doesn't exist yet).

- [ ] **Step 3: Implement subscription router**

Create `backend/app/routers/subscription.py`:

```python
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.models import User, Chat, CalendarEvent, Reminder
from app.schemas.subscription import (
    SubscriptionStatusResponse,
    TrialStatsResponse,
    VerifyRequest,
    VerifyResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/subscription", tags=["subscription"])

TRIAL_DAYS = 7


def _compute_status(user: User) -> tuple[str, int | None]:
    """Return (effective_status, trial_days_left)."""
    if user.subscription_status == "active":
        if user.subscription_expires_at and datetime.now(timezone.utc) > user.subscription_expires_at:
            return "expired", None
        return "active", None

    if user.subscription_status == "trial":
        if user.trial_start_date:
            elapsed = datetime.now(timezone.utc) - user.trial_start_date
            days_left = max(0, TRIAL_DAYS - elapsed.days)
            if days_left == 0:
                return "expired", 0
            return "trial", days_left
        return "trial", TRIAL_DAYS

    return "expired", None


@router.get("/status", response_model=SubscriptionStatusResponse)
async def get_status(
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    status, days_left = _compute_status(user)

    # Auto-update status in DB if trial expired
    if status == "expired" and user.subscription_status != "expired":
        user.subscription_status = "expired"
        await db.commit()

    return SubscriptionStatusResponse(
        status=status,
        trial_days_left=days_left,
        expires_at=user.subscription_expires_at,
    )


@router.get("/trial-stats", response_model=TrialStatsResponse)
async def get_trial_stats(
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # Count chats by this user
    chat_count_q = await db.execute(
        select(func.count()).select_from(Chat).where(Chat.role == "user").join(
            Chat.session
        ).where(Chat.session.has(user_id=user_id))
    )
    chat_count = chat_count_q.scalar() or 0

    # Count reminders
    reminder_count_q = await db.execute(
        select(func.count()).select_from(Reminder).where(Reminder.user_id == user_id)
    )
    reminder_count = reminder_count_q.scalar() or 0

    # Count calendar events
    event_count_q = await db.execute(
        select(func.count()).select_from(CalendarEvent).where(CalendarEvent.user_id == user_id)
    )
    event_count = event_count_q.scalar() or 0

    return TrialStatsResponse(
        chat_count=chat_count,
        reminder_count=reminder_count,
        event_count=event_count,
    )


@router.post("/verify", response_model=VerifyResponse)
async def verify_purchase(
    req: VerifyRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Verify a StoreKit 2 transaction and activate subscription."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    # For now, trust the client transaction (App Store Server Notifications
    # will be the authoritative source for renewals/cancellations)
    user.subscription_status = "active"
    user.subscription_product_id = req.product_id
    # Set expiry based on product type
    if "yearly" in req.product_id:
        user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=365)
    else:
        user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    await db.commit()
    logger.info("subscription_activated", extra={
        "user_id": str(user_id),
        "product_id": req.product_id,
    })

    return VerifyResponse(
        status="active",
        expires_at=user.subscription_expires_at,
    )


@router.post("/webhook")
async def appstore_webhook(
    db: AsyncSession = Depends(get_db),
):
    """App Store Server Notifications V2 webhook.

    TODO: Implement JWS verification and event handling when
    App Store Connect is configured. Events to handle:
    SUBSCRIBED, DID_RENEW, EXPIRED, DID_REVOKE, GRACE_PERIOD_EXPIRED
    """
    # Placeholder — will be implemented when App Store Connect is set up
    return {"status": "ok"}
```

- [ ] **Step 4: Register router in main.py**

In `backend/app/main.py`, add import at line 17:

```python
from app.routers.subscription import router as subscription_router
```

Add router registration after line 53:

```python
app.include_router(subscription_router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_subscription.py -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/subscription.py backend/app/main.py backend/tests/test_subscription.py
git commit -m "feat: add subscription router with status, trial-stats, verify endpoints"
```

---

## Task 4: Backend — Set trial on user creation + write-block middleware

**Files:**
- Modify: `backend/app/routers/auth.py:37-57`
- Create: `backend/app/middleware/subscription.py`

- [ ] **Step 1: Set trial fields on user creation**

In `backend/app/routers/auth.py`, update `_find_or_create_user` (line 43-50). Replace user creation block:

```python
    if user is None:
        user = User(
            id=uuid.uuid4(),
            email=email,
            name=name,
            auth_provider=provider,
            subscription_status="trial",
            trial_start_date=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("user_created", extra={"user_id": str(user.id), "provider": provider})
```

Add `from datetime import datetime, timezone` to the imports at the top of the file.

- [ ] **Step 2: Create subscription check dependency**

Create `backend/app/middleware/subscription.py`:

```python
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.models import User

TRIAL_DAYS = 7

# Paths that expired users can still access
EXEMPT_PREFIXES = ("/api/v1/auth", "/api/v1/subscription")


async def require_active_subscription(
    request: Request,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Dependency that blocks write operations for expired users.

    Add to routers that should be gated:
        @router.post("/...", dependencies=[Depends(require_active_subscription)])
    """
    # Only block write operations
    if request.method == "GET":
        return

    # Exempt paths
    for prefix in EXEMPT_PREFIXES:
        if request.url.path.startswith(prefix):
            return

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return

    # Check trial expiry
    if user.subscription_status == "trial" and user.trial_start_date:
        elapsed = datetime.now(timezone.utc) - user.trial_start_date
        if elapsed > timedelta(days=TRIAL_DAYS):
            user.subscription_status = "expired"
            await db.commit()

    # Check subscription expiry
    if user.subscription_status == "active" and user.subscription_expires_at:
        if datetime.now(timezone.utc) > user.subscription_expires_at:
            user.subscription_status = "expired"
            await db.commit()

    if user.subscription_status == "expired":
        raise HTTPException(
            status_code=403,
            detail={"code": "subscription_expired", "message": "Subscription expired"},
        )
```

- [ ] **Step 3: Wire up subscription check to chat router**

In `backend/app/routers/chat.py`, add the dependency to the chat endpoint. Find the main POST endpoint and add `dependencies=[Depends(require_active_subscription)]`:

```python
from app.middleware.subscription import require_active_subscription

@router.post("/api/v1/chat", dependencies=[Depends(require_active_subscription)])
async def chat(...):
```

Note: Only add to the chat POST endpoint for now. Other routers (calendar, reminders, pets) can be gated later if needed.

- [ ] **Step 4: Run all tests**

```bash
cd backend && pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/auth.py backend/app/middleware/subscription.py backend/app/routers/chat.py
git commit -m "feat: set trial on user creation, add subscription write-block"
```

---

## Task 5: iOS — SubscriptionStore (StoreKit 2)

**Files:**
- Create: `ios-app/CozyPup/Stores/SubscriptionStore.swift`
- Modify: `ios-app/CozyPup/CozyPupApp.swift:59-98`

- [ ] **Step 1: Create SubscriptionStore**

Create `ios-app/CozyPup/Stores/SubscriptionStore.swift`:

```swift
import SwiftUI
import StoreKit

enum SubscriptionStatus: Equatable {
    case loading
    case trial(daysLeft: Int)
    case active
    case expired
}

struct TrialStats: Decodable {
    let chat_count: Int
    let reminder_count: Int
    let event_count: Int
}

@MainActor
class SubscriptionStore: ObservableObject {
    @Published var status: SubscriptionStatus = .loading
    @Published var products: [Product] = []
    @Published var trialStats: TrialStats?
    @Published var isPurchasing = false

    static let productIDs = ["com.cozypup.app.monthly", "com.cozypup.app.yearly"]

    private var transactionListener: Task<Void, Never>?

    init() {
        transactionListener = listenForTransactions()
    }

    deinit {
        transactionListener?.cancel()
    }

    // MARK: - Load

    func loadStatus() async {
        struct StatusResp: Decodable {
            let status: String
            let trial_days_left: Int?
            let expires_at: String?
        }
        do {
            let resp: StatusResp = try await APIClient.shared.request("GET", "/subscription/status")
            switch resp.status {
            case "trial":
                status = .trial(daysLeft: resp.trial_days_left ?? 7)
            case "active":
                status = .active
            default:
                status = .expired
            }
        } catch {
            // If backend unreachable, check StoreKit locally
            await checkStoreKitEntitlements()
        }
    }

    func loadProducts() async {
        do {
            products = try await Product.products(for: Self.productIDs)
                .sorted { $0.price < $1.price }
        } catch {
            print("[Subscription] Failed to load products: \(error)")
        }
    }

    func loadTrialStats() async {
        do {
            trialStats = try await APIClient.shared.request("GET", "/subscription/trial-stats")
        } catch {
            print("[Subscription] Failed to load trial stats: \(error)")
        }
    }

    // MARK: - Purchase

    func purchase(_ product: Product) async throws {
        isPurchasing = true
        defer { isPurchasing = false }

        let result = try await product.purchase()
        switch result {
        case .success(let verification):
            let transaction = try checkVerified(verification)
            await verifyWithBackend(transactionID: String(transaction.id), productID: product.id)
            await transaction.finish()
            status = .active
        case .userCancelled:
            break
        case .pending:
            break
        @unknown default:
            break
        }
    }

    func restorePurchases() async {
        try? await AppStore.sync()
        await checkStoreKitEntitlements()
    }

    // MARK: - Private

    private func listenForTransactions() -> Task<Void, Never> {
        Task.detached {
            for await result in Transaction.updates {
                if let transaction = try? self.checkVerified(result) {
                    await self.verifyWithBackend(
                        transactionID: String(transaction.id),
                        productID: transaction.productID
                    )
                    await transaction.finish()
                    await MainActor.run { self.status = .active }
                }
            }
        }
    }

    private func checkStoreKitEntitlements() async {
        for await result in Transaction.currentEntitlements {
            if let _ = try? checkVerified(result) {
                status = .active
                return
            }
        }
        // No entitlements found — keep current status
    }

    private func checkVerified<T>(_ result: VerificationResult<T>) throws -> T {
        switch result {
        case .unverified:
            throw StoreError.verificationFailed
        case .verified(let value):
            return value
        }
    }

    private func verifyWithBackend(transactionID: String, productID: String) async {
        struct VerifyBody: Encodable {
            let transaction_id: String
            let product_id: String
        }
        struct VerifyResp: Decodable {
            let status: String
            let expires_at: String?
        }
        do {
            let _: VerifyResp = try await APIClient.shared.request(
                "POST", "/subscription/verify",
                body: VerifyBody(transaction_id: transactionID, product_id: productID)
            )
        } catch {
            print("[Subscription] Backend verify failed: \(error)")
        }
    }

    enum StoreError: Error {
        case verificationFailed
    }
}
```

- [ ] **Step 2: Register SubscriptionStore in CozyPupApp**

In `ios-app/CozyPup/CozyPupApp.swift`, add after line 65:

```swift
    @StateObject private var subscriptionStore = SubscriptionStore()
```

Add after line 84 (`.environmentObject(Lang.shared)`):

```swift
            .environmentObject(subscriptionStore)
```

Add a `.task` modifier after `.onOpenURL` block (before the closing `}` of `WindowGroup`) to load subscription status on launch:

```swift
            .task {
                if auth.isAuthenticated {
                    await subscriptionStore.loadStatus()
                    await subscriptionStore.loadProducts()
                }
            }
```

- [ ] **Step 3: Build to verify compilation**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```

Expected: BUILD SUCCEEDED

- [ ] **Step 4: Commit**

```bash
git add ios-app/CozyPup/Stores/SubscriptionStore.swift ios-app/CozyPup/CozyPupApp.swift
git commit -m "feat: add SubscriptionStore with StoreKit 2 integration"
```

---

## Task 6: iOS — Paywall Sheet

**Files:**
- Create: `ios-app/CozyPup/Views/Paywall/PaywallSheet.swift`

- [ ] **Step 1: Create PaywallSheet**

Create `ios-app/CozyPup/Views/Paywall/PaywallSheet.swift`:

```swift
import SwiftUI

struct PaywallSheet: View {
    @EnvironmentObject var subscriptionStore: SubscriptionStore
    let isHard: Bool  // true = expired (no dismiss), false = soft (can dismiss)
    var onDismiss: (() -> Void)? = nil

    @State private var selectedProduct: StoreKit.Product?
    @State private var showPricing = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: Tokens.spacing.lg) {
            // Drag handle
            RoundedRectangle(cornerRadius: 2)
                .fill(Tokens.border)
                .frame(width: 36, height: 4)
                .padding(.top, Tokens.spacing.sm)

            if isHard {
                hardPaywallContent
            } else if showPricing {
                pricingContent
            } else {
                softPaywallContent
            }

            Spacer()
        }
        .padding(.horizontal, Tokens.spacing.md)
        .background(Tokens.bg)
        .task {
            if isHard {
                await subscriptionStore.loadTrialStats()
                await subscriptionStore.loadProducts()
            }
        }
    }

    // MARK: - Soft Paywall

    private var softPaywallContent: some View {
        VStack(spacing: Tokens.spacing.md) {
            // Close button
            if !isHard {
                HStack {
                    Spacer()
                    Button { onDismiss?() } label: {
                        Image(systemName: "xmark")
                            .font(Tokens.fontSubheadline)
                            .foregroundColor(Tokens.textSecondary)
                            .frame(width: 28, height: 28)
                            .background(Tokens.surface)
                            .clipShape(Circle())
                    }
                }
            }

            Text("喜欢 CozyPup 吗？")
                .font(Tokens.fontTitle)
                .foregroundColor(Tokens.text)

            if case .trial(let daysLeft) = subscriptionStore.status {
                Text("试用还剩 \(daysLeft) 天")
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.textSecondary)
            }

            VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                benefitRow("无限 AI 对话 & 健康咨询")
                benefitRow("智能提醒 & 日历管理")
                benefitRow("附近宠物医院搜索")
            }
            .padding(.vertical, Tokens.spacing.sm)

            Button {
                Task {
                    await subscriptionStore.loadProducts()
                }
                withAnimation { showPricing = true }
            } label: {
                Text("查看方案")
                    .font(Tokens.fontBody.weight(.semibold))
                    .foregroundColor(Tokens.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(Tokens.accent)
                    .cornerRadius(Tokens.radiusSmall)
            }

            Button { onDismiss?() } label: {
                Text("暂不需要")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textTertiary)
            }
        }
    }

    // MARK: - Hard Paywall (Data Recap)

    private var hardPaywallContent: some View {
        VStack(spacing: Tokens.spacing.md) {
            Text("这 7 天，CozyPup 帮你")
                .font(Tokens.fontTitle)
                .foregroundColor(Tokens.text)

            if let stats = subscriptionStore.trialStats {
                HStack(spacing: Tokens.spacing.xl) {
                    statBubble(value: stats.chat_count, label: "次对话", color: Tokens.accent)
                    statBubble(value: stats.reminder_count, label: "个提醒", color: Tokens.blue)
                    statBubble(value: stats.event_count, label: "条记录", color: Tokens.green)
                }
                .padding(.vertical, Tokens.spacing.sm)
            }

            Text("继续让 CozyPup 照顾你的毛孩子 🐶")
                .font(Tokens.fontSubheadline)
                .foregroundColor(Tokens.textSecondary)

            pricingContent
        }
    }

    // MARK: - Pricing

    private var pricingContent: some View {
        VStack(spacing: Tokens.spacing.md) {
            HStack(spacing: Tokens.spacing.sm) {
                ForEach(subscriptionStore.products, id: \.id) { product in
                    let isYearly = product.id.contains("yearly")
                    Button {
                        selectedProduct = product
                    } label: {
                        VStack(spacing: Tokens.spacing.xs) {
                            if isYearly {
                                Text("推荐")
                                    .font(Tokens.fontCaption2.weight(.semibold))
                                    .foregroundColor(Tokens.white)
                                    .padding(.horizontal, Tokens.spacing.sm)
                                    .padding(.vertical, 2)
                                    .background(Tokens.accent)
                                    .cornerRadius(Tokens.spacing.sm)
                            }
                            Text(isYearly ? "年付" : "月付")
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textSecondary)
                            Text(product.displayPrice)
                                .font(Tokens.fontTitle)
                                .foregroundColor(Tokens.text)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, Tokens.spacing.md)
                        .background(
                            selectedProduct?.id == product.id
                                ? Tokens.accentSoft
                                : Tokens.surface
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                                .stroke(
                                    selectedProduct?.id == product.id
                                        ? Tokens.accent
                                        : Tokens.border,
                                    lineWidth: 1.5
                                )
                        )
                        .cornerRadius(Tokens.radiusSmall)
                    }
                }
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.red)
            }

            Button {
                guard let product = selectedProduct ?? subscriptionStore.products.last else { return }
                Task {
                    do {
                        try await subscriptionStore.purchase(product)
                        onDismiss?()
                    } catch {
                        errorMessage = error.localizedDescription
                    }
                }
            } label: {
                if subscriptionStore.isPurchasing {
                    ProgressView()
                        .tint(Tokens.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Tokens.accent.opacity(0.7))
                        .cornerRadius(Tokens.radiusSmall)
                } else {
                    Text("订阅")
                        .font(Tokens.fontBody.weight(.semibold))
                        .foregroundColor(Tokens.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Tokens.accent)
                        .cornerRadius(Tokens.radiusSmall)
                }
            }
            .disabled(subscriptionStore.isPurchasing)

            Button {
                Task { await subscriptionStore.restorePurchases() }
            } label: {
                Text("恢复购买")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textTertiary)
            }
        }
    }

    // MARK: - Components

    private func benefitRow(_ text: String) -> some View {
        HStack(spacing: Tokens.spacing.sm) {
            Image(systemName: "checkmark")
                .font(Tokens.fontCaption.weight(.bold))
                .foregroundColor(Tokens.accent)
            Text(text)
                .font(Tokens.fontBody)
                .foregroundColor(Tokens.text)
        }
    }

    private func statBubble(value: Int, label: String, color: Color) -> some View {
        VStack(spacing: Tokens.spacing.xxs) {
            Text("\(value)")
                .font(Tokens.fontTitle.weight(.bold))
                .foregroundColor(color)
            Text(label)
                .font(Tokens.fontCaption)
                .foregroundColor(Tokens.textSecondary)
        }
    }
}

#Preview("Soft") {
    PaywallSheet(isHard: false)
        .environmentObject(SubscriptionStore())
        .presentationDetents([.medium])
}

#Preview("Hard") {
    PaywallSheet(isHard: true)
        .environmentObject(SubscriptionStore())
        .presentationDetents([.medium])
}
```

- [ ] **Step 2: Build to verify**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
git add ios-app/CozyPup/Views/Paywall/PaywallSheet.swift
git commit -m "feat: add PaywallSheet with soft and hard paywall modes"
```

---

## Task 7: iOS — Quick Action Cards + Welcome Message

**Files:**
- Create: `ios-app/CozyPup/Views/Chat/QuickActionCards.swift`
- Modify: `ios-app/CozyPup/Views/Chat/ChatView.swift:63-82`
- Modify: `ios-app/CozyPup/Stores/ChatStore.swift`

- [ ] **Step 1: Create QuickActionCards component**

Create `ios-app/CozyPup/Views/Chat/QuickActionCards.swift`:

```swift
import SwiftUI

struct QuickActionCards: View {
    let onSelect: (String) -> Void

    private let actions: [(icon: String, label: String, message: String)] = [
        ("🐶", "添加宠物", "我想添加一只宠物"),
        ("💊", "健康咨询", "我家宠物最近有点不舒服"),
        ("📅", "设个提醒", "帮我设一个提醒"),
        ("📍", "附近医院", "帮我找附近的宠物医院"),
    ]

    var body: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: Tokens.spacing.sm) {
            ForEach(actions, id: \.label) { action in
                Button {
                    Haptics.light()
                    onSelect(action.message)
                } label: {
                    VStack(spacing: Tokens.spacing.xs) {
                        Text(action.icon)
                            .font(.title2)
                        Text(action.label)
                            .font(Tokens.fontSubheadline.weight(.medium))
                            .foregroundColor(Tokens.text)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, Tokens.spacing.md)
                    .background(Tokens.surface)
                    .cornerRadius(Tokens.radiusSmall)
                }
            }
        }
        .padding(.horizontal, Tokens.spacing.md)
    }
}

#Preview {
    QuickActionCards { msg in print(msg) }
        .background(Tokens.bg)
}
```

- [ ] **Step 2: Add welcome message flag to ChatStore**

In `ios-app/CozyPup/Stores/ChatStore.swift`, add a property and helper:

```swift
    private let welcomeKey = "cozypup_has_seen_welcome"

    var hasSeenWelcome: Bool {
        get { UserDefaults.standard.bool(forKey: welcomeKey) }
        set { UserDefaults.standard.set(newValue, forKey: welcomeKey) }
    }
```

- [ ] **Step 3: Replace empty state in ChatView with quick-action cards**

In `ios-app/CozyPup/Views/Chat/ChatView.swift`, replace the empty state block (lines 66-82) with:

```swift
                            if chatStore.messages.isEmpty {
                                VStack(spacing: Tokens.spacing.md) {
                                    // Welcome message (first time only)
                                    if !chatStore.hasSeenWelcome {
                                        HStack(alignment: .top, spacing: Tokens.spacing.sm) {
                                            Image("logo")
                                                .resizable()
                                                .frame(width: 28, height: 28)
                                                .cornerRadius(14)
                                            Text("你好！我是 CozyPup，你的宠物专属管家 🐾\n\n我可以帮你：记录健康状况、设置疫苗提醒、查找附近宠物医院、解答养宠问题。\n\n先告诉我你家毛孩子叫什么吧～")
                                                .font(Tokens.fontBody)
                                                .foregroundColor(Tokens.text)
                                                .padding(Tokens.spacing.md)
                                                .background(Tokens.bubbleAi)
                                                .cornerRadius(Tokens.radius)
                                        }
                                        .padding(.horizontal, Tokens.spacing.md)
                                        .padding(.top, Tokens.spacing.xl)
                                    }

                                    Spacer()

                                    // Quick action cards
                                    QuickActionCards { message in
                                        inputText = message
                                        sendMessage()
                                        chatStore.hasSeenWelcome = true
                                    }
                                    .padding(.bottom, Tokens.spacing.lg)
                                }
                                .frame(minHeight: 400)
                            }
```

- [ ] **Step 4: Build to verify**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```

Expected: BUILD SUCCEEDED

- [ ] **Step 5: Commit**

```bash
git add ios-app/CozyPup/Views/Chat/QuickActionCards.swift \
        ios-app/CozyPup/Views/Chat/ChatView.swift \
        ios-app/CozyPup/Stores/ChatStore.swift
git commit -m "feat: add quick-action cards and welcome message for new users"
```

---

## Task 8: iOS — Placeholder rotation in ChatInputBar

**Files:**
- Modify: `ios-app/CozyPup/Views/Chat/ChatInputBar.swift`

- [ ] **Step 1: Add rotating placeholder to ChatInputBar**

In `ios-app/CozyPup/Views/Chat/ChatInputBar.swift`, add state and timer at the top of the struct:

```swift
    private let placeholders = [
        "试试说：我家狗最近老挠耳朵…",
        "试试说：帮我记一下今天打了疫苗",
        "试试说：下周三提醒我去宠物店",
    ]
    @State private var placeholderIndex = 0
```

Replace the existing static placeholder in the `TextField` with `placeholders[placeholderIndex]`.

Add a timer modifier to the `TextField` or its container:

```swift
    .onReceive(Timer.publish(every: 4, on: .main, in: .common).autoconnect()) { _ in
        withAnimation(.easeInOut(duration: 0.3)) {
            placeholderIndex = (placeholderIndex + 1) % placeholders.count
        }
    }
```

- [ ] **Step 2: Build to verify**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
git add ios-app/CozyPup/Views/Chat/ChatInputBar.swift
git commit -m "feat: add rotating placeholder hints in chat input"
```

---

## Task 9: iOS — Wire up paywall triggers

**Files:**
- Modify: `ios-app/CozyPup/Views/Chat/ChatView.swift`
- Modify: `ios-app/CozyPup/Stores/ChatStore.swift`
- Modify: `ios-app/CozyPup/Views/Settings/SettingsDrawer.swift`

- [ ] **Step 1: Add message count tracking to ChatStore**

In `ios-app/CozyPup/Stores/ChatStore.swift`, add:

```swift
    private let messageCountKey = "cozypup_total_message_count"

    var totalMessageCount: Int {
        get { UserDefaults.standard.integer(forKey: messageCountKey) }
        set { UserDefaults.standard.set(newValue, forKey: messageCountKey) }
    }

    private let softPaywallCountKey = "cozypup_soft_paywall_count"
    private let softPaywallDateKey = "cozypup_soft_paywall_date"

    var softPaywallShownCount: Int {
        get { UserDefaults.standard.integer(forKey: softPaywallCountKey) }
        set { UserDefaults.standard.set(newValue, forKey: softPaywallCountKey) }
    }

    var lastSoftPaywallDate: Date? {
        get { UserDefaults.standard.object(forKey: softPaywallDateKey) as? Date }
        set { UserDefaults.standard.set(newValue, forKey: softPaywallDateKey) }
    }

    func incrementMessageCount() {
        totalMessageCount += 1
    }
```

- [ ] **Step 2: Add paywall trigger logic to ChatView**

In `ios-app/CozyPup/Views/Chat/ChatView.swift`, add state and environment:

```swift
    @EnvironmentObject var subscriptionStore: SubscriptionStore
    @State private var showSoftPaywall = false
    @State private var showHardPaywall = false
```

Add `.sheet` modifiers after the main `ZStack`:

```swift
    .sheet(isPresented: $showSoftPaywall) {
        PaywallSheet(isHard: false) { showSoftPaywall = false }
            .presentationDetents([.medium])
            .environmentObject(subscriptionStore)
    }
    .sheet(isPresented: $showHardPaywall) {
        PaywallSheet(isHard: true)
            .presentationDetents([.medium])
            .interactiveDismissDisabled(true)
            .environmentObject(subscriptionStore)
    }
    .task {
        // Check if expired on appear
        if case .expired = subscriptionStore.status {
            showHardPaywall = true
        }
    }
    .onChange(of: subscriptionStore.status) { _, newStatus in
        if case .expired = newStatus {
            showHardPaywall = true
        }
    }
```

In the `sendMessage` function, after sending a message, add the soft paywall check:

```swift
    chatStore.incrementMessageCount()
    // Soft paywall: 10+ messages, 24h+ since registration, max 2 times
    if case .trial(let daysLeft) = subscriptionStore.status,
       daysLeft < 7,  // at least 24h since registration
       chatStore.totalMessageCount >= 10,
       chatStore.softPaywallShownCount < 2 {
        // Don't show if already shown today
        if chatStore.lastSoftPaywallDate == nil ||
           !Calendar.current.isDateInToday(chatStore.lastSoftPaywallDate!) {
            showSoftPaywall = true
            chatStore.softPaywallShownCount += 1
            chatStore.lastSoftPaywallDate = Date()
        }
    }
```

- [ ] **Step 3: Disable input when expired**

In `ChatView.swift`, wrap the `ChatInputBar` with a subscription check:

```swift
    if case .expired = subscriptionStore.status {
        Text("订阅后继续对话")
            .font(Tokens.fontSubheadline)
            .foregroundColor(Tokens.textTertiary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, Tokens.spacing.md)
            .background(Tokens.surface)
            .onTapGesture { showHardPaywall = true }
    } else {
        ChatInputBar(...)  // existing input bar
    }
```

- [ ] **Step 4: Add subscription status to SettingsDrawer**

In `ios-app/CozyPup/Views/Settings/SettingsDrawer.swift`, add `@EnvironmentObject var subscriptionStore: SubscriptionStore` and add a section in the settings list after user profile:

```swift
    // Subscription section
    VStack(spacing: 0) {
        HStack {
            Image(systemName: "crown.fill")
                .foregroundColor(Tokens.accent)
                .frame(width: Tokens.size.avatarSmall)
            Text("会员状态")
                .font(Tokens.fontBody)
                .foregroundColor(Tokens.text)
            Spacer()
            Group {
                switch subscriptionStore.status {
                case .trial(let days):
                    Text("试用中 · \(days)天")
                        .foregroundColor(Tokens.orange)
                case .active:
                    Text("已订阅")
                        .foregroundColor(Tokens.green)
                case .expired:
                    Text("已过期")
                        .foregroundColor(Tokens.red)
                case .loading:
                    ProgressView()
                }
            }
            .font(Tokens.fontSubheadline)
        }
        .padding(.vertical, Tokens.spacing.sm)
        .padding(.horizontal, Tokens.spacing.md)
        .contentShape(Rectangle())
        .onTapGesture {
            if case .expired = subscriptionStore.status {
                showPaywall = true
            }
        }
    }
    .background(Tokens.surface)
    .cornerRadius(Tokens.radiusSmall)
```

Add `@State private var showPaywall = false` and a `.sheet` modifier for the paywall.

- [ ] **Step 5: Build to verify**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```

Expected: BUILD SUCCEEDED

- [ ] **Step 6: Commit**

```bash
git add ios-app/CozyPup/Views/Chat/ChatView.swift \
        ios-app/CozyPup/Stores/ChatStore.swift \
        ios-app/CozyPup/Views/Settings/SettingsDrawer.swift
git commit -m "feat: wire up soft/hard paywall triggers and expired state UI"
```

---

## Task 10: Handle 403 subscription_expired in APIClient

**Files:**
- Modify: `ios-app/CozyPup/Services/APIClient.swift`

- [ ] **Step 1: Add subscription expired error handling**

In `ios-app/CozyPup/Services/APIClient.swift`, add a new error case to the `APIError` enum:

```swift
    case subscriptionExpired
```

In the `request` method, after checking for HTTP status codes, add handling for 403:

```swift
    if http.statusCode == 403 {
        // Check if it's a subscription expiry
        if let body = try? JSONDecoder().decode([String: String].self, from: data),
           body["code"] == "subscription_expired" {
            throw APIError.subscriptionExpired
        }
    }
```

- [ ] **Step 2: Post notification on subscription expired**

When `.subscriptionExpired` is caught, post a notification so the UI can react:

```swift
    // In the caller (e.g., ChatView sendMessage error handling):
    } catch APIError.subscriptionExpired {
        await subscriptionStore.loadStatus()  // refresh status
        // UI will react to status change via .onChange
    }
```

- [ ] **Step 3: Build to verify**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```

Expected: BUILD SUCCEEDED

- [ ] **Step 4: Commit**

```bash
git add ios-app/CozyPup/Services/APIClient.swift
git commit -m "feat: handle subscription_expired 403 in APIClient"
```

---

## Task 11: Backend tests + full integration test

**Files:**
- Modify: `backend/tests/test_subscription.py`

- [ ] **Step 1: Add write-block test**

Add to `backend/tests/test_subscription.py`:

```python
@pytest.mark.asyncio
async def test_expired_user_blocked_from_chat(expired_user, auth_headers):
    """Expired users should get 403 on POST /chat."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/chat",
            headers={**auth_headers, "Content-Type": "application/json"},
            json={"message": "hello"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "subscription_expired"


@pytest.mark.asyncio
async def test_expired_user_can_read(expired_user, auth_headers):
    """Expired users should still be able to GET endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/pets", headers=auth_headers)
    # Should not be 403 — read access is allowed
    assert resp.status_code != 403


@pytest.mark.asyncio
async def test_verify_activates_subscription(trial_user, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/subscription/verify",
            headers={**auth_headers, "Content-Type": "application/json"},
            json={"transaction_id": "12345", "product_id": "com.cozypup.app.monthly"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
```

- [ ] **Step 2: Run all tests**

```bash
cd backend && pytest tests/test_subscription.py -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_subscription.py
git commit -m "test: add subscription write-block and verify tests"
```

---

## Task 12: Database migration for existing users

**Files:**
- Create: Alembic data migration

- [ ] **Step 1: Create data migration for existing users**

```bash
cd backend && alembic revision -m "set existing users to active subscription"
```

Edit the generated migration file:

```python
def upgrade():
    # Existing users get "active" status so they're not affected
    op.execute("""
        UPDATE users
        SET subscription_status = 'active'
        WHERE subscription_status = 'trial'
        AND trial_start_date IS NULL
    """)


def downgrade():
    pass
```

- [ ] **Step 2: Apply migration**

```bash
alembic upgrade head
```

Expected: Migration applied successfully.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat: migrate existing users to active subscription status"
```
