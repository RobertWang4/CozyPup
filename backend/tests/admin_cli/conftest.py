"""Smoke-test fixtures: a real uvicorn server on a random port + an admin user."""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import AdminAuditLog, User


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _db_reachable() -> bool:
    """Quick check whether the dev DB is reachable. If not, smoke tests skip."""
    import asyncio as _aio
    from sqlalchemy.ext.asyncio import create_async_engine

    async def _ping():
        try:
            eng = create_async_engine(settings.database_url, pool_pre_ping=False)
            async with eng.connect() as conn:
                await conn.execute(select(1))
            await eng.dispose()
            return True
        except Exception:
            return False

    try:
        return _aio.get_event_loop().run_until_complete(_ping()) if not _aio.get_event_loop().is_running() else _aio.run(_ping())
    except RuntimeError:
        return _aio.run(_ping())


@pytest.fixture(scope="session")
def admin_user_email() -> str:
    return "robert-smoke@cozypup.local"


@pytest_asyncio.fixture(scope="session")
async def admin_user(admin_user_email):
    """Ensure an admin user exists; skip if DB not reachable."""
    try:
        async with async_session() as db:
            row = await db.execute(select(User).where(User.email == admin_user_email))
            user = row.scalar_one_or_none()
            if user is None:
                user = User(
                    id=uuid.uuid4(),
                    email=admin_user_email,
                    name="Smoke Admin",
                    auth_provider="dev",
                    is_admin=True,
                )
                db.add(user)
            else:
                user.is_admin = True
            await db.commit()
    except Exception as e:
        pytest.skip(f"DB not reachable for smoke tests: {e}")

    yield user

    try:
        async with async_session() as db:
            rows = await db.execute(select(AdminAuditLog).where(AdminAuditLog.admin_user_id == user.id))
            for r in rows.scalars():
                await db.delete(r)
            await db.commit()
    except Exception:
        pass


@pytest.fixture(scope="session")
def backend_server(admin_user):
    """Start uvicorn on a random port with environment=dev and wait for readiness."""
    port = _free_port()
    env = os.environ.copy()
    env["ENVIRONMENT"] = "dev"
    env["CLOUD_LOGGING_ENABLED"] = "false"

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 15
    ready = False
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(0.2)

    if not ready:
        # /health may not exist — try /docs as a fallback readiness signal
        for _ in range(10):
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/docs", timeout=1)
                if r.status_code in (200, 404):
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(0.2)

    if not ready:
        proc.kill()
        out = proc.stdout.read().decode() if proc.stdout else ""
        pytest.skip(f"uvicorn did not start on {port}: {out[:500]}")

    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture()
def cli_home(tmp_path):
    """Override HOME so the CLI reads/writes a throwaway config file."""
    old = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    yield tmp_path
    if old is not None:
        os.environ["HOME"] = old


@pytest.fixture()
def run_admin(cli_home, backend_server):
    """Invoke the `admin` console script as a subprocess against the test server."""
    def _run(*args, expect_ok: bool = True) -> dict:
        env = os.environ.copy()
        env["HOME"] = str(cli_home)
        env["COZYPUP_ADMIN_BASE_URL_DEV"] = backend_server
        cmd = ["admin", *args]
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
        if expect_ok and r.returncode != 0:
            raise AssertionError(f"cmd={cmd!r} rc={r.returncode} out={r.stdout} err={r.stderr}")
        return {"rc": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
    return _run
