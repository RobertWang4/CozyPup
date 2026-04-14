"""Tests for /api/v1/admin/subscriptions/*."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers.admin.deps import AdminContext, require_admin


def _ctx():
    u = MagicMock(); u.id = uuid.uuid4(); u.email = "robert@x.com"; u.is_admin = True
    return AdminContext(user=u, scope="admin", token_iat=0, ip="1.1.1.1", correlation_id="c")


def _target(product_id="com.cozypup.pro_monthly", duo=False):
    u = MagicMock()
    u.id = uuid.uuid4(); u.email = "alice@x.com"
    u.subscription_status = "active"
    u.subscription_product_id = product_id if not duo else "com.cozypup.pro.duo"
    u.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=10)
    u.family_role = None
    u.family_payer_id = None
    return u


@pytest.mark.asyncio
async def test_show_returns_subscription_state(monkeypatch):
    from app.routers.admin import subscriptions as mod
    target = _target()
    async def _fake_resolve(db, t): return target
    monkeypatch.setattr(mod, "_resolve_user", _fake_resolve)

    app.dependency_overrides[require_admin] = lambda: _ctx()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/admin/subscriptions/alice@x.com", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["status"] == "active"
        assert body["product_id"] == "com.cozypup.pro_monthly"
        assert body["is_duo"] is False
    finally:
        app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_extend_adds_days_and_audits(monkeypatch):
    from app.routers.admin import subscriptions as mod
    target = _target()
    original_expiry = target.subscription_expires_at
    async def _fake_resolve(db, t): return target
    monkeypatch.setattr(mod, "_resolve_user", _fake_resolve)

    async def _fake_db():
        db = AsyncMock(); db.add = MagicMock(); db.flush = AsyncMock()
        yield db

    from app.database import get_db
    app.dependency_overrides[require_admin] = lambda: _ctx()
    app.dependency_overrides[get_db] = _fake_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/admin/subscriptions/alice@x.com/extend",
                json={"reason": "goodwill", "days": 30},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 200
        env = r.json()
        assert env["audit_id"]
        assert target.subscription_expires_at == original_expiry + timedelta(days=30)
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_extend_duo_requires_force(monkeypatch):
    from app.routers.admin import subscriptions as mod
    target = _target(duo=True)
    async def _fake_resolve(db, t): return target
    monkeypatch.setattr(mod, "_resolve_user", _fake_resolve)

    async def _fake_db():
        db = AsyncMock(); db.add = MagicMock(); db.flush = AsyncMock()
        yield db

    from app.database import get_db
    app.dependency_overrides[require_admin] = lambda: _ctx()
    app.dependency_overrides[get_db] = _fake_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # without force_duo → 409
            r = await ac.post(
                "/api/v1/admin/subscriptions/alice@x.com/extend",
                json={"reason": "goodwill", "days": 7},
                headers={"Authorization": "Bearer x"},
            )
            assert r.status_code == 409

            # with force_duo → 200
            r = await ac.post(
                "/api/v1/admin/subscriptions/alice@x.com/extend",
                json={"reason": "goodwill", "days": 7, "force_duo": True},
                headers={"Authorization": "Bearer x"},
            )
            assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_revoke_sets_expired_status(monkeypatch):
    from app.routers.admin import subscriptions as mod
    target = _target()
    async def _fake_resolve(db, t): return target
    monkeypatch.setattr(mod, "_resolve_user", _fake_resolve)

    async def _fake_db():
        db = AsyncMock(); db.add = MagicMock(); db.flush = AsyncMock()
        yield db

    from app.database import get_db
    app.dependency_overrides[require_admin] = lambda: _ctx()
    app.dependency_overrides[get_db] = _fake_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/admin/subscriptions/alice@x.com/revoke",
                json={"reason": "chargeback"},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 200
        assert target.subscription_status == "expired"
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)
