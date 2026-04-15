"""E2E tests for Family/Duo subscription (TEST_PLAN.md SS43).

Tests cover the Duo subscription family invite/accept/revoke lifecycle,
permission controls, and subscription gating after revocation.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from tests.e2e.conftest import E2EClient, BASE_URL

# Duo product ID used across tests (matches _is_duo_product check: ".duo" in product_id)
DUO_PRODUCT = "com.cozypup.duo.monthly"
INDIVIDUAL_PRODUCT = "com.cozypup.individual.monthly"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def duo_pair(base_url):
    """Two fresh users: A (Duo subscriber) and B (trial).

    A is set up with an active Duo subscription so invite tests work
    without needing a real StoreKit transaction.
    """
    a = E2EClient(base_url)
    b = E2EClient(base_url)
    await a.auth_dev()
    await b.auth_dev()
    # Give A an active Duo subscription
    await a.set_subscription(status="active", product_id=DUO_PRODUCT)
    yield a, b
    await a.close()
    await b.close()


@pytest_asyncio.fixture
async def trio(base_url):
    """Three fresh users: A (Duo), B (trial), C (trial)."""
    a = E2EClient(base_url)
    b = E2EClient(base_url)
    c = E2EClient(base_url)
    await a.auth_dev()
    await b.auth_dev()
    await c.auth_dev()
    await a.set_subscription(status="active", product_id=DUO_PRODUCT)
    yield a, b, c
    await a.close()
    await b.close()
    await c.close()


# ---------------------------------------------------------------------------
# SS43a. Invite flow
# ---------------------------------------------------------------------------

class TestInviteFlow:
    """43.1-43.4: Full invite -> accept -> status verification."""

    @pytest.mark.asyncio
    async def test_43_1_invite_created(self, duo_pair):
        """43.1: A (Duo) invites B by email -> invite created."""
        a, b = duo_pair
        result = await a.invite_family(b.email)
        assert result["status_code"] == 200, f"Invite failed: {result}"
        assert result["status"] == "pending"
        assert result.get("invite_id"), "Missing invite_id"
        assert result.get("invite_url"), "Missing invite_url"

        # Verify A's family status shows pending invite
        status = await a.get_family_status()
        assert status["invite_pending"] is True
        assert status["pending_invite_id"] == result["invite_id"]

    @pytest.mark.asyncio
    async def test_43_2_accept_invite(self, duo_pair):
        """43.2: B accepts invite -> B gets active subscription."""
        a, b = duo_pair
        invite = await a.invite_family(b.email)
        assert invite["status_code"] == 200

        accept = await b.accept_family(invite["invite_id"])
        assert accept["status_code"] == 200, f"Accept failed: {accept}"
        assert accept["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_43_3_payer_status(self, duo_pair):
        """43.3: After accept, A's status shows role=payer with member info."""
        a, b = duo_pair
        invite = await a.invite_family(b.email)
        await b.accept_family(invite["invite_id"])

        status = await a.get_family_status()
        assert status["role"] == "payer"
        assert status.get("partner_email") is not None

    @pytest.mark.asyncio
    async def test_43_4_member_status(self, duo_pair):
        """43.4: After accept, B's status shows role=member."""
        a, b = duo_pair
        invite = await a.invite_family(b.email)
        await b.accept_family(invite["invite_id"])

        status = await b.get_family_status()
        assert status["role"] == "member"
        assert status.get("partner_email") is not None


# ---------------------------------------------------------------------------
# SS43c. Permission control
# ---------------------------------------------------------------------------

class TestPermissionControl:
    """43.7-43.8: Subscription and capacity checks."""

    @pytest.mark.asyncio
    async def test_43_7_individual_cannot_invite(self, base_url):
        """43.7: A (Individual subscription) tries to invite -> rejected."""
        a = E2EClient(base_url)
        b = E2EClient(base_url)
        try:
            await a.auth_dev()
            await b.auth_dev()
            # Give A an Individual (non-Duo) subscription
            await a.set_subscription(status="active", product_id=INDIVIDUAL_PRODUCT)

            result = await a.invite_family(b.email)
            assert result["status_code"] == 400, f"Expected 400, got {result['status_code']}"
            assert "duo" in result.get("detail", "").lower() or "Duo" in result.get("detail", "")
        finally:
            await a.close()
            await b.close()

    @pytest.mark.asyncio
    async def test_43_8_max_one_member(self, trio):
        """43.8: A (already has member B) invites C -> rejected."""
        a, b, c = trio
        # A invites and B accepts
        invite = await a.invite_family(b.email)
        assert invite["status_code"] == 200
        accept = await b.accept_family(invite["invite_id"])
        assert accept["status_code"] == 200

        # Now A tries to invite C -> should be rejected
        result = await a.invite_family(c.email)
        assert result["status_code"] == 400, f"Expected 400, got {result['status_code']}"
        assert "already" in result.get("detail", "").lower()


# ---------------------------------------------------------------------------
# SS43d. Revoke
# ---------------------------------------------------------------------------

class TestRevoke:
    """43.9-43.10: Revoke partner and subscription gating."""

    @pytest.mark.asyncio
    async def test_43_9_revoke_member(self, duo_pair):
        """43.9: A revokes member -> B's family_role=null, subscription expired."""
        a, b = duo_pair
        invite = await a.invite_family(b.email)
        await b.accept_family(invite["invite_id"])

        # Verify B is a member before revoke
        status_before = await b.get_family_status()
        assert status_before["role"] == "member"

        # A revokes
        revoke = await a.revoke_family()
        assert revoke["status_code"] == 200
        assert revoke["status"] == "revoked"

        # B should no longer be a member
        status_after = await b.get_family_status()
        assert status_after["role"] is None

    @pytest.mark.asyncio
    async def test_43_10_chat_after_revoke(self, duo_pair):
        """43.10: B tries to chat after revoke -> blocked by subscription gate.

        The chat endpoint does not return 403; instead it sends a canned SSE
        stream with an ``upgrade_prompt`` card and a short message telling
        the user their trial/subscription has ended.
        """
        a, b = duo_pair
        invite = await a.invite_family(b.email)
        await b.accept_family(invite["invite_id"])

        # A revokes B
        await a.revoke_family()

        # B's subscription is now expired; chat should return upgrade prompt.
        result = await b.chat("hello")
        assert result.has_card("upgrade_prompt"), (
            f"Expected upgrade_prompt card after revoke. "
            f"Cards: {[c.get('type') for c in result.cards]}, "
            f"Text: {result.text}"
        )
