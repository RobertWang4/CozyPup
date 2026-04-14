"""Tests for /api/v1/admin/ops/*."""
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


@pytest.mark.asyncio
async def test_ratelimit_clear_single_user(monkeypatch):
    from app.routers.admin import ops as mod
    from app.middleware import rate_limit
    rate_limit._buckets.clear()
    rate_limit._buckets["alice"].timestamps.append(1.0)

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
                "/api/v1/admin/ops/ratelimit/clear",
                json={"reason": "smoke", "user_key": "alice"},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 200
        assert "alice" not in rate_limit._buckets
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_flags_set_writes_db(monkeypatch):
    from app.routers.admin import ops as mod
    from app import flags

    written = {}

    async def _upsert(key, value, description, user_id, db):
        written["key"] = key
        written["value"] = value
        flags._set_in_cache(key, value)
        return True

    monkeypatch.setattr(mod, "_upsert_flag", _upsert)

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
                "/api/v1/admin/ops/flags/set",
                json={"reason": "turn off dev auth", "key": "auth_dev_enabled", "value": False},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 200
        assert written["key"] == "auth_dev_enabled"
        assert written["value"] is False
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_session_revoke_inserts_token_revocation(monkeypatch):
    from app.routers.admin import ops as mod

    target = MagicMock(); target.id = uuid.uuid4(); target.email = "alice@x.com"
    async def _fake_resolve(db, t): return target
    monkeypatch.setattr(mod, "_resolve_user", _fake_resolve)

    inserted = {}

    async def _upsert(user_id, reason, db):
        inserted["user_id"] = user_id
        inserted["reason"] = reason
        return True

    monkeypatch.setattr(mod, "_upsert_revocation", _upsert)

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
                "/api/v1/admin/ops/session/revoke",
                json={"reason": "stolen device", "target": "alice@x.com"},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 200
        assert inserted["user_id"] == target.id
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_cache_flush_is_stub():
    app.dependency_overrides[require_admin] = lambda: _ctx()

    async def _fake_db():
        db = AsyncMock(); db.add = MagicMock(); db.flush = AsyncMock()
        yield db

    from app.database import get_db
    app.dependency_overrides[get_db] = _fake_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/admin/ops/cache/flush",
                json={"reason": "smoke", "key": "pets:u1"},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 200
        assert r.json()["data"]["stub"] is True
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)
