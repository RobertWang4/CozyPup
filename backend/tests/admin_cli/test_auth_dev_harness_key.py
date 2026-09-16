"""Tests that /auth/dev is closed in production unless X-Harness-Key matches."""
import pytest
from httpx import ASGITransport, AsyncClient

from app import flags
from app.config import settings
from app.main import app


@pytest.fixture
def prod_env(monkeypatch):
    flags._cache.clear()
    flags._set_in_cache("auth_dev_enabled", True)
    monkeypatch.setattr(settings, "environment", "production")
    yield
    flags._cache.clear()


async def _post_dev(headers: dict | None = None):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.post(
            "/api/v1/auth/dev",
            json={"email": "x@y.com", "name": "Test"},
            headers=headers or {},
        )


@pytest.mark.asyncio
async def test_prod_closed_when_no_key_configured(prod_env, monkeypatch):
    monkeypatch.setattr(settings, "harness_api_key", "")
    r = await _post_dev(headers={"X-Harness-Key": "anything"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_prod_closed_without_header(prod_env, monkeypatch):
    monkeypatch.setattr(settings, "harness_api_key", "s3cret")
    r = await _post_dev()
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_prod_closed_with_wrong_key(prod_env, monkeypatch):
    monkeypatch.setattr(settings, "harness_api_key", "s3cret")
    r = await _post_dev(headers={"X-Harness-Key": "wrong"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_prod_open_with_matching_key(prod_env, monkeypatch):
    monkeypatch.setattr(settings, "harness_api_key", "s3cret")
    # Only assert the gate lets the request through (not short-circuited to 404).
    r = await _post_dev(headers={"X-Harness-Key": "s3cret"})
    assert r.status_code != 404


@pytest.mark.asyncio
async def test_dev_env_ignores_key(monkeypatch):
    flags._cache.clear()
    flags._set_in_cache("auth_dev_enabled", True)
    monkeypatch.setattr(settings, "environment", "dev")
    monkeypatch.setattr(settings, "harness_api_key", "s3cret")
    r = await _post_dev()
    assert r.status_code != 404
