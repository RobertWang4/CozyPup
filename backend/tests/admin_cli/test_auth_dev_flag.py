"""Tests that /auth/dev honors the auth_dev_enabled feature flag."""
import pytest
from httpx import ASGITransport, AsyncClient

from app import flags
from app.main import app


@pytest.mark.asyncio
async def test_auth_dev_blocked_when_flag_false(monkeypatch):
    flags._cache.clear()
    flags._set_in_cache("auth_dev_enabled", False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/api/v1/auth/dev", json={"email": "x@y.com", "name": "Test"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_auth_dev_allowed_when_flag_true(monkeypatch):
    flags._cache.clear()
    flags._set_in_cache("auth_dev_enabled", True)
    # We don't need the endpoint to succeed end-to-end — just verify it's NOT
    # short-circuited to 404 by the flag gate.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/api/v1/auth/dev", json={"email": "x@y.com", "name": "Test"})
    assert r.status_code != 404
