"""Tests for /api/v1/admin/auth/* endpoints."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


@pytest.mark.asyncio
async def test_dev_login_returns_admin_token_when_env_is_dev(monkeypatch):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "robert@x.com"
    user.is_admin = True

    res = MagicMock()
    res.scalar_one_or_none.return_value = user
    db = AsyncMock()
    db.execute.return_value = res

    from app.database import get_db
    async def _dep():
        yield db
    app.dependency_overrides[get_db] = _dep

    monkeypatch.setattr(settings, "environment", "dev", raising=False)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/admin/auth/dev-login", json={"email": "robert@x.com"})
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["scope"] == "admin"
        assert body["data"]["expires_in"] > 0
        assert body["data"]["token"]
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_dev_login_rejects_non_admin_user(monkeypatch):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "mallory@x.com"
    user.is_admin = False

    res = MagicMock()
    res.scalar_one_or_none.return_value = user
    db = AsyncMock()
    db.execute.return_value = res

    from app.database import get_db
    async def _dep():
        yield db
    app.dependency_overrides[get_db] = _dep
    monkeypatch.setattr(settings, "environment", "dev", raising=False)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/admin/auth/dev-login", json={"email": "mallory@x.com"})
        assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_dev_login_disabled_in_prod(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production", raising=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/api/v1/admin/auth/dev-login", json={"email": "robert@x.com"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_whoami_returns_scope_and_email():
    from app.routers.admin.deps import require_admin, AdminContext

    async def _fake():
        u = type("U", (), {})()
        u.id = uuid.uuid4()
        u.email = "robert@x.com"
        u.is_admin = True
        return AdminContext(user=u, scope="admin", token_iat=0, ip="1.1.1.1", correlation_id="c")

    app.dependency_overrides[require_admin] = _fake
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/admin/auth/whoami", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["email"] == "robert@x.com"
        assert body["data"]["scope"] == "admin"
    finally:
        app.dependency_overrides.pop(require_admin, None)
