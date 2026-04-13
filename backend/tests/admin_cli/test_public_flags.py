"""Public /api/v1/flags/public endpoint returns the allow-listed subset."""
import pytest
from httpx import ASGITransport, AsyncClient

from app import flags
from app.main import app


@pytest.mark.asyncio
async def test_public_flags_returns_banner_and_safe_flags():
    flags._cache.clear()
    flags._set_in_cache("broadcast_banner", {"text": "maintenance at 10pm", "severity": "info"})
    flags._set_in_cache("auth_dev_enabled", False)   # should NOT leak
    flags._set_in_cache("chat_rate_limit_per_hour", 30)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/v1/flags/public")
    assert r.status_code == 200
    data = r.json()
    assert data["broadcast_banner"]["text"] == "maintenance at 10pm"
    assert "auth_dev_enabled" not in data
    assert data["chat_rate_limit_per_hour"] == 30
