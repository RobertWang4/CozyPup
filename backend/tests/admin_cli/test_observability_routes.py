"""Tests for /api/v1/admin/users/{id}/inspect and friends."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers.admin.deps import AdminContext, require_admin


def _ctx(**over):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = "robert@x.com"
    u.is_admin = True
    return AdminContext(user=u, scope="admin", token_iat=0, ip="1.1.1.1", correlation_id="c")


@pytest.mark.asyncio
async def test_inspect_returns_envelope_with_profile_and_activity(monkeypatch):
    from app.routers.admin import observability as obs

    async def _fake_inspect(*, target, since, chats_mode, session_id, db, gcloud_reader):
        return {
            "user": {"id": "u1", "email": "alice@x.com", "created_at": "2026-02-14"},
            "subscription": {"status": "active", "product": "pro", "expires_at": "2026-05-01"},
            "pets": [{"id": "p1", "name": "dou", "species": "dog"}],
            "counters": {"messages_24h": 14, "errors_24h": 1, "tokens_24h": 42000},
            "activity": [{"ts": "2026-04-12T10:02:00Z", "role": "user", "correlation_id": "cid-a", "content": "hi", "error": None}],
        }

    monkeypatch.setattr(obs, "inspect_user", _fake_inspect)
    app.dependency_overrides[require_admin] = lambda: _ctx()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(
                "/api/v1/admin/users/alice@x.com/inspect?since=24h&chats=recent",
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 200, r.text
        env = r.json()
        assert env["data"]["user"]["email"] == "alice@x.com"
        assert env["data"]["activity"][0]["correlation_id"] == "cid-a"
        assert "audit_id" in env
    finally:
        app.dependency_overrides.pop(require_admin, None)
