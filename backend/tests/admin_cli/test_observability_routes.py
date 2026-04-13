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


@pytest.mark.asyncio
async def test_trace_reconstructs_pipeline(monkeypatch):
    from app.routers.admin import observability as obs

    async def _fake(target_cid, *, gcloud_reader, db, show_tools=False, show_system_prompt=False):
        return {
            "correlation_id": target_cid,
            "chat_request": {"message": "hi", "pet_snapshot": [], "session_history_tail": [], "image_urls_full": []},
            "rounds": [
                {
                    "round": 0,
                    "llm_request": {"model": "grok", "message_count": 3},
                    "llm_response": {"content": "ok", "tool_calls": [], "prompt_tokens": 10, "completion_tokens": 20},
                    "tool_calls": [],
                }
            ],
            "chat_response": {"text_length": 2},
            "error": None,
        }

    monkeypatch.setattr(obs, "reconstruct_trace", _fake)
    app.dependency_overrides[require_admin] = lambda: _ctx()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/admin/traces/abc123", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        env = r.json()
        assert env["data"]["correlation_id"] == "abc123"
        assert env["data"]["rounds"][0]["round"] == 0
    finally:
        app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_errors_recent_groups(monkeypatch):
    from app.routers.admin import observability as obs

    async def _fake(*, since, module, user_id, group_by, db, gcloud_reader):
        return {"groups": [{"key": "app.agents.orchestrator:KeyError", "count": 3, "sample_cid": "c1", "last_seen": "2026-04-12T10:02:00Z"}]}

    monkeypatch.setattr(obs, "recent_errors", _fake)
    app.dependency_overrides[require_admin] = lambda: _ctx()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/admin/errors?since=24h", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        assert r.json()["data"]["groups"][0]["count"] == 3
    finally:
        app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_impersonate_requires_reason_and_returns_token(monkeypatch):
    from app.routers.admin import observability as obs

    async def _fake_resolve(db, target):
        u = MagicMock()
        u.id = uuid.uuid4()
        u.email = "alice@x.com"
        u.is_admin = False
        return u

    monkeypatch.setattr(obs, "_resolve_user", _fake_resolve)
    app.dependency_overrides[require_admin] = lambda: _ctx()

    async def _fake_db():
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        yield db

    from app.database import get_db
    app.dependency_overrides[get_db] = _fake_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/admin/users/alice@x.com/impersonate",
                json={"ttl_minutes": 10},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 422

        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/admin/users/alice@x.com/impersonate",
                json={"ttl_minutes": 10, "reason": "bug repro"},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 200
        env = r.json()
        assert env["data"]["token"]
        assert env["data"]["scope"] == "user"
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_export_returns_redacted_bundle(monkeypatch):
    from app.routers.admin import observability as obs

    async def _fake_resolve(db, target):
        u = MagicMock()
        u.id = uuid.uuid4()
        u.email = "alice@x.com"
        u.name = "Alice"
        u.password_hash = "REDACT_ME"
        return u

    async def _fake_bundle(user, db, gcloud_reader=None):
        return {"users": [{"id": str(user.id), "email": "alice@x.com", "password_hash": None}], "pets": [], "chats": [], "chat_sessions": [], "calendar_events": [], "reminders": [], "traces": [], "audit": []}

    monkeypatch.setattr(obs, "_resolve_user", _fake_resolve)
    monkeypatch.setattr(obs, "build_export_bundle", _fake_bundle)

    async def _fake_db():
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        yield db

    from app.database import get_db
    app.dependency_overrides[require_admin] = lambda: _ctx()
    app.dependency_overrides[get_db] = _fake_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/v1/admin/users/alice@x.com/export",
                json={"reason": "gdpr"},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 200, r.text
        env = r.json()
        assert env["data"]["users"][0]["password_hash"] is None
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)
