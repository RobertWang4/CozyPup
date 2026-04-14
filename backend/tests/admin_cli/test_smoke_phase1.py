# backend/tests/admin_cli/test_smoke_phase1.py
"""Phase 1 CLI smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import AdminAuditLog


def _env(stdout: str) -> dict:
    obj = json.loads(stdout)
    assert set(obj.keys()) >= {"data", "audit_id", "env"}
    return obj


@pytest.mark.asyncio
async def test_phase1_smoke(run_admin, admin_user, admin_user_email, seeded_chat, tmp_path, query_db):
    # Pre-req: login
    run_admin("login", "--dev", "--email", admin_user_email, "--env", "dev", "--json")

    # admin user inspect
    r = run_admin("user", "inspect", admin_user_email, "--since", "24h", "--chats", "recent", "--json")
    env = _env(r["stdout"])
    assert env["data"]["user"]["email"] == admin_user_email
    assert any(a.get("correlation_id") == seeded_chat["cid"] for a in env["data"]["activity"])

    # admin trace <cid> — gcloud entries may be empty in smoke; endpoint must still succeed
    r = run_admin("trace", seeded_chat["cid"], "--json")
    env = _env(r["stdout"])
    assert env["data"]["correlation_id"] == seeded_chat["cid"]

    # admin errors recent
    r = run_admin("errors", "recent", "--since", "24h", "--json")
    env = _env(r["stdout"])
    assert "groups" in env["data"]

    # admin user export (audited write)
    out = tmp_path / "export.json"
    r = run_admin("user", "export", admin_user_email, "--reason", "smoke-export", "--out", str(out), "--json")
    env = _env(r["stdout"])
    assert out.exists(), "export file missing"
    bundle = json.loads(out.read_text())
    assert bundle["users"][0]["email"] == admin_user_email
    assert bundle["users"][0].get("password_hash") is None

    audit_id_export = env["audit_id"]
    assert audit_id_export, "export must emit audit_id"

    # admin user impersonate (audited write)
    r = run_admin("user", "impersonate", admin_user_email, "--reason", "smoke-impersonate", "--ttl", "5", "--json")
    env = _env(r["stdout"])
    assert env["data"]["scope"] == "user"
    assert env["data"]["token"]
    audit_id_imp = env["audit_id"]
    assert audit_id_imp

    # Verify both audit rows exist with correct actions
    rows = await query_db(select(AdminAuditLog).where(AdminAuditLog.action.in_(["user.export", "user.impersonate"])))
    found_actions = {(r.action, str(r.id)) for r in rows}
    assert ("user.export", audit_id_export) in found_actions
    assert ("user.impersonate", audit_id_imp) in found_actions


@pytest.mark.asyncio
async def test_phase1_impersonate_rejects_missing_reason(run_admin, admin_user_email):
    run_admin("login", "--dev", "--email", admin_user_email, "--env", "dev", "--json")
    # Click requires --reason; missing it makes click exit non-zero.
    r = run_admin("user", "impersonate", admin_user_email, "--ttl", "5", "--json", expect_ok=False)
    assert r["rc"] != 0
