"""Tests for subscription router logic."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth import get_current_user_id
from app.database import Base, get_db
from app.main import app
from app.routers.subscription import _compute_status, TRIAL_DAYS
from app.models import User


def _make_user(
    status="trial",
    trial_start_date=None,
    subscription_expires_at=None,
    product_id=None,
):
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.subscription_status = status
    user.trial_start_date = trial_start_date
    user.subscription_expires_at = subscription_expires_at
    user.subscription_product_id = product_id
    return user


class TestComputeStatus:
    def test_trial_user_with_recent_start_returns_trial(self):
        user = _make_user(
            status="trial",
            trial_start_date=datetime.now(timezone.utc) - timedelta(days=2),
        )
        status, days_left = _compute_status(user)
        assert status == "trial"
        assert days_left == TRIAL_DAYS - 2

    def test_trial_user_without_start_date_returns_full_trial(self):
        user = _make_user(status="trial", trial_start_date=None)
        status, days_left = _compute_status(user)
        assert status == "trial"
        assert days_left == TRIAL_DAYS

    def test_trial_user_expired_8_days_ago_returns_expired(self):
        user = _make_user(
            status="trial",
            trial_start_date=datetime.now(timezone.utc) - timedelta(days=8),
        )
        status, days_left = _compute_status(user)
        assert status == "expired"
        assert days_left == 0

    def test_trial_user_exactly_at_limit_returns_expired(self):
        user = _make_user(
            status="trial",
            trial_start_date=datetime.now(timezone.utc) - timedelta(days=TRIAL_DAYS),
        )
        status, days_left = _compute_status(user)
        assert status == "expired"
        assert days_left == 0

    def test_active_subscription_not_expired(self):
        user = _make_user(
            status="active",
            subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        status, days_left = _compute_status(user)
        assert status == "active"
        assert days_left is None

    def test_active_subscription_past_expiry_returns_expired(self):
        user = _make_user(
            status="active",
            subscription_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        status, days_left = _compute_status(user)
        assert status == "expired"
        assert days_left is None

    def test_active_subscription_no_expiry_date_returns_active(self):
        user = _make_user(status="active", subscription_expires_at=None)
        status, days_left = _compute_status(user)
        assert status == "active"
        assert days_left is None

    def test_already_expired_status_returns_expired(self):
        user = _make_user(status="expired")
        status, days_left = _compute_status(user)
        assert status == "expired"
        assert days_left is None


class TestGetStatusEndpoint:
    @pytest.mark.asyncio
    async def test_subscription_status_trial(self):
        """New user in trial returns trial status with days_left."""
        from app.routers.subscription import get_status

        user = _make_user(
            status="trial",
            trial_start_date=datetime.now(timezone.utc) - timedelta(days=1),
        )

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = user

        db = AsyncMock()
        db.execute.return_value = mock_result

        response = await get_status(user_id=user.id, db=db)

        assert response.status == "trial"
        assert response.trial_days_left == TRIAL_DAYS - 1

    @pytest.mark.asyncio
    async def test_subscription_status_expired(self):
        """User whose trial started 8 days ago returns expired status."""
        from app.routers.subscription import get_status

        user = _make_user(
            status="trial",
            trial_start_date=datetime.now(timezone.utc) - timedelta(days=8),
        )

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = user

        db = AsyncMock()
        db.execute.return_value = mock_result
        db.commit = AsyncMock()

        response = await get_status(user_id=user.id, db=db)

        assert response.status == "expired"
        assert response.trial_days_left == 0
        # Should have auto-updated status and committed
        assert user.subscription_status == "expired"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_subscription_status_active(self):
        """Active subscriber returns active status."""
        from app.routers.subscription import get_status

        expires = datetime.now(timezone.utc) + timedelta(days=25)
        user = _make_user(status="active", subscription_expires_at=expires)

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = user

        db = AsyncMock()
        db.execute.return_value = mock_result

        response = await get_status(user_id=user.id, db=db)

        assert response.status == "active"
        assert response.trial_days_left is None
        assert response.expires_at == expires


class TestTrialStatsEndpoint:
    @pytest.mark.asyncio
    async def test_trial_stats_returns_counts(self):
        """Returns chat_count, reminder_count, event_count from DB."""
        from app.routers.subscription import get_trial_stats

        user_id = uuid.uuid4()

        # DB returns different scalars for each query: chats=5, reminders=3, events=7
        db = AsyncMock()
        results = []
        for count in [5, 3, 7]:
            r = MagicMock()
            r.scalar.return_value = count
            results.append(r)
        db.execute.side_effect = results

        response = await get_trial_stats(user_id=user_id, db=db)

        assert response.chat_count == 5
        assert response.reminder_count == 3
        assert response.event_count == 7

    @pytest.mark.asyncio
    async def test_trial_stats_zero_counts(self):
        """Returns zeros when user has no data."""
        from app.routers.subscription import get_trial_stats

        user_id = uuid.uuid4()

        db = AsyncMock()
        results = []
        for count in [None, None, None]:
            r = MagicMock()
            r.scalar.return_value = count
            results.append(r)
        db.execute.side_effect = results

        response = await get_trial_stats(user_id=user_id, db=db)

        assert response.chat_count == 0
        assert response.reminder_count == 0
        assert response.event_count == 0


class TestVerifyEndpoint:
    @pytest.mark.asyncio
    async def test_verify_monthly_purchase_sets_active(self):
        """Verifying a monthly product sets active status with 30-day expiry."""
        from app.routers.subscription import verify_purchase
        from app.schemas.subscription import VerifyRequest

        user = _make_user(status="trial")

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = user

        db = AsyncMock()
        db.execute.return_value = mock_result
        db.commit = AsyncMock()

        req = VerifyRequest(
            transaction_id="txn_abc123",
            product_id="com.cozypup.monthly",
        )

        response = await verify_purchase(req=req, user_id=user.id, db=db)

        assert response.status == "active"
        assert response.expires_at is not None
        assert user.subscription_status == "active"
        assert user.subscription_product_id == "com.cozypup.monthly"
        db.commit.assert_awaited_once()

        # Expiry should be ~30 days from now
        delta = response.expires_at - datetime.now(timezone.utc)
        assert 29 <= delta.days <= 30

    @pytest.mark.asyncio
    async def test_verify_yearly_purchase_sets_365_day_expiry(self):
        """Verifying a yearly product sets 365-day expiry."""
        from app.routers.subscription import verify_purchase
        from app.schemas.subscription import VerifyRequest

        user = _make_user(status="trial")

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = user

        db = AsyncMock()
        db.execute.return_value = mock_result
        db.commit = AsyncMock()

        req = VerifyRequest(
            transaction_id="txn_yearly123",
            product_id="com.cozypup.yearly",
        )

        response = await verify_purchase(req=req, user_id=user.id, db=db)

        assert response.status == "active"
        delta = response.expires_at - datetime.now(timezone.utc)
        assert 364 <= delta.days <= 365


# ---------------------------------------------------------------------------
# HTTP-level integration tests (TestClient + in-memory SQLite)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def _sqlite_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def _db(_sqlite_engine):
    factory = async_sessionmaker(
        _sqlite_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


def _http_client(db_session: AsyncSession, user_id: uuid.UUID) -> TestClient:
    """Build a TestClient with DB and auth overrides."""

    async def _override_db():
        yield db_session

    async def _override_user_id():
        return user_id

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user_id] = _override_user_id
    client = TestClient(app, raise_server_exceptions=False)
    return client


async def _create_user(
    db: AsyncSession,
    *,
    status: str = "trial",
    trial_start_date=None,
    subscription_expires_at=None,
) -> User:
    # SQLite stores datetimes without timezone, so strip tzinfo to avoid
    # "can't subtract offset-naive and offset-aware datetimes" errors when
    # the middleware/router reads values back from the DB.
    def _naive(dt):
        return dt.replace(tzinfo=None) if dt is not None else None

    user = User(
        id=uuid.uuid4(),
        email=f"test_{uuid.uuid4().hex[:6]}@example.com",
        auth_provider="dev",
        subscription_status=status,
        trial_start_date=_naive(trial_start_date),
        subscription_expires_at=_naive(subscription_expires_at),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


class TestExpiredUserBlockedFromChat:
    @pytest.mark.asyncio
    async def test_expired_user_gets_403_on_post_chat(self, _db):
        """User with expired subscription → POST /chat returns 403 subscription_expired.

        The trial→expired promotion (trial_start_date arithmetic) is covered by unit
        tests in TestComputeStatus. Here we test the HTTP gate with a user whose status
        is already stored as 'expired' in the DB — the same state after auto-promotion.
        """
        user = await _create_user(_db, status="expired")
        client = _http_client(_db, user.id)
        try:
            response = client.post(
                "/api/v1/chat",
                json={"message": "hello", "session_id": None},
            )
            assert response.status_code == 403
            body = response.json()
            assert body["detail"]["code"] == "subscription_expired"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_active_trial_user_is_not_blocked(self, _db):
        """User in active trial (no trial_start_date set yet) is NOT blocked on POST /chat."""
        # No trial_start_date → middleware sees trial with None → skips date check → no block.
        # The chat endpoint itself may error for other reasons; we only care it isn't 403
        # with code='subscription_expired'.
        user = await _create_user(_db, status="trial")
        client = _http_client(_db, user.id)
        try:
            response = client.post(
                "/api/v1/chat",
                json={"message": "hello", "session_id": None},
            )
            assert response.status_code != 403 or (
                response.json().get("detail", {}).get("code") != "subscription_expired"
            )
        finally:
            app.dependency_overrides.clear()


class TestExpiredUserCanRead:
    @pytest.mark.asyncio
    async def test_expired_user_can_get_pets(self, _db):
        """Expired user can still call GET /pets — read endpoints are never blocked."""
        user = await _create_user(_db, status="expired")
        client = _http_client(_db, user.id)
        try:
            response = client.get("/api/v1/pets")
            # 200 (empty list) — NOT 403
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_expired_user_can_get_subscription_status(self, _db):
        """Expired user can read /subscription/status — GET is always allowed."""
        user = await _create_user(_db, status="expired")
        client = _http_client(_db, user.id)
        try:
            response = client.get("/api/v1/subscription/status")
            assert response.status_code == 200
            assert response.json()["status"] == "expired"
        finally:
            app.dependency_overrides.clear()


class TestVerifyActivatesSubscription:
    @pytest.mark.asyncio
    async def test_verify_sets_active_status_and_returns_expires_at(self, _db):
        """POST /subscription/verify with a valid transaction activates the subscription."""
        user = await _create_user(_db, status="trial")
        client = _http_client(_db, user.id)
        try:
            response = client.post(
                "/api/v1/subscription/verify",
                json={
                    "transaction_id": "txn_test_001",
                    "product_id": "com.cozypup.monthly",
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "active"
            assert body["expires_at"] is not None
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_verify_allows_post_chat_after_activation(self, _db):
        """After verify, an expired user should no longer be blocked on POST /chat."""
        user = await _create_user(_db, status="expired")
        client = _http_client(_db, user.id)
        try:
            # Activate subscription
            verify_resp = client.post(
                "/api/v1/subscription/verify",
                json={
                    "transaction_id": "txn_test_002",
                    "product_id": "com.cozypup.monthly",
                },
            )
            assert verify_resp.status_code == 200

            # POST /chat should now pass the subscription gate (may fail for other
            # reasons like missing session, but not 403 subscription_expired)
            chat_resp = client.post(
                "/api/v1/chat",
                json={"message": "hello", "session_id": None},
            )
            assert chat_resp.status_code != 403
            if chat_resp.status_code == 403:
                assert chat_resp.json().get("detail", {}).get("code") != "subscription_expired"
        finally:
            app.dependency_overrides.clear()
