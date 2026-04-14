"""Phase 3 CLI smoke test: ops, flags, audit, session revoke."""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models import AdminAuditLog, FeatureFlag, TokenRevocation, User


def _env(stdout: str) -> dict:
    obj = json.loads(stdout)
    assert set(obj.keys()) >= {"data", "audit_id", "env"}
    return obj


@pytest_asyncio.fixture()
async def e3_victim():
    email = f"e3-{uuid.uuid4().hex[:8]}@cozypup.local"
    try:
        eng = create_async_engine(settings.database_url, poolclass=NullPool)
        async with AsyncSession(eng) as db:
            u = User(id=uuid.uuid4(), email=email, name="E3 Victim", auth_provider="dev", is_admin=False)
            db.add(u)
            await db.commit()
        await eng.dispose()
    except Exception as e:
        pytest.skip(f"DB not reachable: {e}")
    yield {"email": email}
    try:
        eng = create_async_engine(settings.database_url, poolclass=NullPool)
        async with AsyncSession(eng) as db:
            await db.execute(User.__table__.delete().where(User.email == email))
            await db.commit()
        await eng.dispose()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_phase3_flags_set_get_unset(run_admin, admin_user_email, query_db):
    run_admin("login", "--dev", "--email", admin_user_email, "--env", "dev", "--json")

    r = run_admin("ops", "flags", "set", "smoke_flag", "true", "--reason", "phase3-smoke", "--json")
    env = _env(r["stdout"])
    assert env["audit_id"]

    r = run_admin("ops", "flags", "get", "smoke_flag", "--json")
    env = _env(r["stdout"])
    assert env["data"]["value"] is True

    r = run_admin("ops", "flags", "unset", "smoke_flag", "--reason", "cleanup", "--json")
    env = _env(r["stdout"])
    assert env["audit_id"]

    rows = await query_db(select(FeatureFlag).where(FeatureFlag.key == "smoke_flag"))
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_phase3_session_revoke(run_admin, admin_user_email, e3_victim, query_db):
    run_admin("login", "--dev", "--email", admin_user_email, "--env", "dev", "--json")

    r = run_admin("ops", "session", "revoke", e3_victim["email"], "--reason", "stolen device", "--json")
    env = _env(r["stdout"])
    assert env["audit_id"]

    users = await query_db(select(User).where(User.email == e3_victim["email"]))
    target = users[0]
    revocations = await query_db(select(TokenRevocation).where(TokenRevocation.user_id == target.id))
    assert len(revocations) > 0


@pytest.mark.asyncio
async def test_phase3_audit_list_sees_recent_writes(run_admin, admin_user_email):
    run_admin("login", "--dev", "--email", admin_user_email, "--env", "dev", "--json")
    # Ping to generate a guaranteed audit row in the window.
    run_admin("ping", "--reason", "phase3-audit-seed", "--json")

    r = run_admin("audit", "list", "--since", "1h", "--limit", "5", "--json")
    env = _env(r["stdout"])
    assert any(row["action"] == "admin.ping" for row in env["data"])
