# backend/tests/admin_cli/test_smoke_phase2.py
"""Phase 2 CLI smoke test: user writes + subscription writes."""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.database import async_session
from app.models import AdminAuditLog, User


@pytest_asyncio.fixture()
async def victim_user():
    email = f"victim-{uuid.uuid4().hex[:8]}@cozypup.local"
    try:
        async with async_session() as db:
            u = User(id=uuid.uuid4(), email=email, name="Victim", auth_provider="dev", is_admin=False)
            db.add(u)
            await db.commit()
    except Exception as e:
        pytest.skip(f"DB not reachable: {e}")

    yield {"email": email}

    try:
        async with async_session() as db:
            await db.execute(User.__table__.delete().where(User.email == email))
            await db.commit()
    except Exception:
        pass


def _env(stdout: str) -> dict:
    obj = json.loads(stdout)
    assert set(obj.keys()) >= {"data", "audit_id", "env"}
    return obj


@pytest.mark.asyncio
async def test_phase2_user_writes(run_admin, admin_user, admin_user_email, victim_user):
    run_admin("login", "--dev", "--email", admin_user_email, "--env", "dev", "--json")

    # search
    r = run_admin("user", "search", victim_user["email"], "--json")
    env = _env(r["stdout"])
    assert any(u["email"] == victim_user["email"] for u in env["data"])

    # ban
    r = run_admin("user", "ban", victim_user["email"], "--days", "7", "--reason", "smoke-ban", "--json")
    env = _env(r["stdout"])
    assert env["data"]["banned_until"]

    # unban
    r = run_admin("user", "unban", victim_user["email"], "--reason", "smoke-unban", "--json")
    env = _env(r["stdout"])
    assert env["data"]["banned_until"] is None

    # grant-admin
    r = run_admin("user", "grant-admin", victim_user["email"], "--reason", "smoke-grant", "--json")
    env = _env(r["stdout"])
    assert env["data"]["is_admin"] is True

    # revoke-admin
    r = run_admin("user", "revoke-admin", victim_user["email"], "--reason", "smoke-revoke", "--json")
    env = _env(r["stdout"])
    assert env["data"]["is_admin"] is False

    # Audit rows exist for every write
    async with async_session() as db:
        rows = (await db.execute(select(AdminAuditLog).where(AdminAuditLog.action.in_(["user.ban", "user.unban", "user.grant_admin", "user.revoke_admin"])))).scalars().all()
        actions = {r.action for r in rows}
    assert {"user.ban", "user.unban", "user.grant_admin", "user.revoke_admin"} <= actions


@pytest.mark.asyncio
async def test_phase2_sub_writes(run_admin, admin_user_email, victim_user):
    run_admin("login", "--dev", "--email", admin_user_email, "--env", "dev", "--json")

    # extend: new user starts on trial; extend adds days and flips status to active
    r = run_admin("sub", "extend", victim_user["email"], "--days", "14", "--reason", "smoke-extend", "--json")
    env = _env(r["stdout"])
    assert env["data"]["status"] == "active"
    assert env["audit_id"]

    # revoke
    r = run_admin("sub", "revoke", victim_user["email"], "--reason", "smoke-revoke", "--json")
    env = _env(r["stdout"])
    assert env["data"]["status"] == "expired"

    # Both audit rows
    async with async_session() as db:
        rows = (await db.execute(select(AdminAuditLog).where(AdminAuditLog.action.in_(["sub.extend", "sub.revoke"])))).scalars().all()
        assert {r.action for r in rows} >= {"sub.extend", "sub.revoke"}
