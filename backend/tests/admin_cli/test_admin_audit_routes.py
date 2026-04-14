"""Tests for /api/v1/admin/audit/*."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers.admin.deps import AdminContext, require_admin


def _ctx():
    u = MagicMock(); u.id = uuid.uuid4(); u.email = "robert@x.com"; u.is_admin = True
    return AdminContext(user=u, scope="admin", token_iat=0, ip="1.1.1.1", correlation_id="c")


@pytest.mark.asyncio
async def test_audit_list_returns_rows(monkeypatch):
    from app.routers.admin import audit as mod

    async def _fake_list(*, since, admin_email, target_user, action, limit, db):
        return [
            {
                "id": str(uuid.uuid4()),
                "action": "sub.extend",
                "admin_user_id": str(uuid.uuid4()),
                "target_type": "user",
                "target_id": "u1",
                "args_json": {"reason": "goodwill", "days": 30},
                "created_at": "2026-04-12T10:00:00Z",
            }
        ]

    monkeypatch.setattr(mod, "list_audit", _fake_list)
    app.dependency_overrides[require_admin] = lambda: _ctx()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/admin/audit?since=24h", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        assert r.json()["data"][0]["action"] == "sub.extend"
    finally:
        app.dependency_overrides.pop(require_admin, None)
