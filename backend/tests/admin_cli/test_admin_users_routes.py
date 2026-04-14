"""Tests for /api/v1/admin/users/* write routes."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers.admin.deps import AdminContext, require_admin


def _ctx():
    u = MagicMock(); u.id = uuid.uuid4(); u.email = "robert@x.com"; u.is_admin = True
    return AdminContext(user=u, scope="admin", token_iat=0, ip="1.1.1.1", correlation_id="c")


def _target():
    u = MagicMock(); u.id = uuid.uuid4(); u.email = "alice@x.com"
    u.is_admin = False; u.banned_until = None; u.deleted_at = None
    u.subscription_status = "trial"; u.subscription_product_id = None
    return u


@pytest.mark.asyncio
async def test_ban_sets_banned_until_and_audits(monkeypatch):
    from app.routers.admin import users as mod

    target = _target()
    async def _fake_resolve(db, t): return target
    monkeypatch.setattr(mod, "_resolve_user", _fake_resolve)

    async def _fake_db():
        db = AsyncMock(); db.add = MagicMock(); db.flush = AsyncMock(); db.commit = AsyncMock()
        yield db

    from app.database import get_db
    app.dependency_overrides[require_admin] = lambda: _ctx()
    app.dependency_overrides[get_db] = _fake_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/admin/users/alice@x.com/ban",
                json={"reason": "spam", "days": 7},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 200, r.text
        env = r.json()
        assert env["data"]["banned_until"]
        assert env["audit_id"]
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_delete_refuses_with_active_paid_sub(monkeypatch):
    from app.routers.admin import users as mod

    paid = _target()
    paid.subscription_status = "active"; paid.subscription_product_id = "com.cozypup.pro_monthly"
    async def _fake_resolve(db, t): return paid
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
                "/api/v1/admin/users/alice@x.com/delete",
                json={"reason": "user request"},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 409
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_grant_admin_flips_flag(monkeypatch):
    from app.routers.admin import users as mod

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
                "/api/v1/admin/users/alice@x.com/grant-admin",
                json={"reason": "bootstrap"},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 200
        assert target.is_admin is True
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_search_returns_matches(monkeypatch):
    from app.routers.admin import users as mod

    async def _fake_search(*, q, limit, db):
        return [{"id": "u1", "email": "alice@x.com", "name": "Alice", "is_admin": False}]

    monkeypatch.setattr(mod, "search_users", _fake_search)
    app.dependency_overrides[require_admin] = lambda: _ctx()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/admin/users/search?q=alice", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        assert r.json()["data"][0]["email"] == "alice@x.com"
    finally:
        app.dependency_overrides.pop(require_admin, None)
