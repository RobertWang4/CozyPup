"""Tests for subscription router logic."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
