"""End-to-end test for /api/v1/admin/ping using the FastAPI test client."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import create_access_token
from app.database import get_db
from app.main import app
from app.routers.admin.deps import require_admin, AdminContext


def _override_admin(user_is_admin=True):
    async def _fake():
        user = type("U", (), {})()
        user.id = uuid.uuid4()
        user.email = "robert@x.com"
        user.is_admin = user_is_admin
        return AdminContext(user=user, scope="admin", token_iat=0, ip="127.0.0.1", correlation_id="cid")
    return _fake


def _override_db():
    """Return a mock AsyncSession that satisfies audit_write (add + flush)."""
    async def _fake_db():
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        # Give the audit row a real id so str(row.id) works
        def _add_side(row):
            row.id = uuid.uuid4()
        db.add.side_effect = _add_side
        yield db
    return _fake_db


@pytest.mark.asyncio
async def test_ping_admin_returns_ok():
    app.dependency_overrides[require_admin] = _override_admin(True)
    app.dependency_overrides[get_db] = _override_db()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/admin/ping",
                json={"reason": "smoke"},
                headers={"Authorization": "Bearer fake"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["pong"] is True
        assert "audit_id" in body
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_ping_unauthenticated_is_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/api/v1/admin/ping", json={"reason": "smoke"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_ping_missing_reason_is_422():
    app.dependency_overrides[require_admin] = _override_admin(True)
    app.dependency_overrides[get_db] = _override_db()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/admin/ping", json={}, headers={"Authorization": "Bearer fake"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)
