"""Tests for AdminClient: base URL resolution, envelope decoding, auth header."""
import json

import httpx
import pytest
import respx

from app.admin_cli.client import AdminClient, AdminClientError
from app.admin_cli.config import AdminConfig


def _cfg(token="tok", env="dev"):
    return AdminConfig(token=token, token_expires_at=9999999999, default_env=env, email="r@x.com")


def test_base_url_dev():
    c = AdminClient(_cfg(env="dev"))
    assert c.base_url == "http://localhost:8000"


def test_base_url_prod():
    c = AdminClient(_cfg(env="prod"))
    assert c.base_url == "https://backend-601329501885.northamerica-northeast1.run.app"


@respx.mock
def test_post_sends_bearer_and_unwraps_envelope():
    respx.post("http://localhost:8000/api/v1/admin/ping").mock(
        return_value=httpx.Response(200, json={"data": {"pong": True}, "audit_id": "a1", "env": "dev"})
    )
    c = AdminClient(_cfg())
    env = c.post("/admin/ping", {"reason": "smoke"})
    assert env.data == {"pong": True}
    assert env.audit_id == "a1"
    assert env.env == "dev"
    sent = respx.calls.last.request
    assert sent.headers["Authorization"] == "Bearer tok"


@respx.mock
def test_404_raises_without_token_leak():
    respx.post("http://localhost:8000/api/v1/admin/ping").mock(
        return_value=httpx.Response(404, json={"detail": "Not Found"})
    )
    c = AdminClient(_cfg())
    with pytest.raises(AdminClientError) as exc:
        c.post("/admin/ping", {"reason": "smoke"})
    assert "404" in str(exc.value)
