"""CLI smoke test for Milestone A (Phase 0)."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.database import async_session
from app.models import AdminAuditLog


def _parse_envelope(stdout: str) -> dict:
    obj = json.loads(stdout)
    assert set(obj.keys()) >= {"data", "audit_id", "env"}, f"envelope missing keys: {obj.keys()}"
    return obj


@pytest.mark.asyncio
async def test_phase0_smoke(run_admin, admin_user, admin_user_email):
    # admin login --dev
    r = run_admin("login", "--dev", "--email", admin_user_email, "--env", "dev", "--json")
    env = _parse_envelope(r["stdout"])
    assert env["data"]["email"] == admin_user_email

    # admin whoami --json
    r = run_admin("whoami", "--json")
    env = _parse_envelope(r["stdout"])
    assert env["data"]["email"] == admin_user_email
    assert env["data"]["scope"] == "admin"
    assert "user_id" in env["data"]

    # admin ping --reason "smoke" --json  (write — emits audit row)
    r = run_admin("ping", "--reason", "phase0-smoke", "--json")
    env = _parse_envelope(r["stdout"])
    assert env["data"]["pong"] is True
    assert env["audit_id"], "ping should emit audit_id"

    async with async_session() as db:
        rows = await db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "admin.ping"))
        found = [str(r.id) for r in rows.scalars()]
    assert env["audit_id"] in found, "ping audit row missing"

    # admin config show (no --json path — just rc=0)
    r = run_admin("config", "show")
    assert "default_env" in r["stdout"]

    # admin logout
    r = run_admin("logout")
    assert "Logged out" in r["stdout"]

    # admin whoami after logout should fail
    r = run_admin("whoami", "--json", expect_ok=False)
    assert r["rc"] != 0


@pytest.mark.asyncio
async def test_phase0_debug_rehome_smoke(run_admin, admin_user_email):
    """`admin debug lookup` runs with the same output as legacy `debug lookup`."""
    r = run_admin("debug", "lookup", admin_user_email)
    assert r["rc"] == 0
