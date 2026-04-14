"""Tests for audit_write decorator: persists rows with args+result and requires reason."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from app.models import AdminAuditLog
from app.routers.admin.deps import AdminContext, audit_write


class _Body(BaseModel):
    reason: str = ""
    days: int = 0


def _ctx(db):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "robert@x.com"
    user.is_admin = True
    return AdminContext(user=user, scope="admin", token_iat=0, ip="1.2.3.4", correlation_id="cid1")


@pytest.mark.asyncio
async def test_audit_write_rejects_empty_reason():
    @audit_write(action="sub.extend", target_type="user")
    async def handler(user_id: uuid.UUID, body: _Body, ctx: AdminContext):
        return {"ok": True}

    db = AsyncMock()
    ctx = _ctx(db); ctx_db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await handler(user_id=uuid.uuid4(), body=_Body(reason="", days=7), ctx=ctx, db=ctx_db)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_audit_write_persists_row_on_success():
    captured = {}

    @audit_write(action="sub.extend", target_type="user")
    async def handler(user_id: uuid.UUID, body: _Body, ctx: AdminContext):
        return {"ok": True, "days": body.days}

    db = AsyncMock()
    db.add = MagicMock(side_effect=lambda row: captured.setdefault("row", row))
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    ctx = _ctx(db)
    tid = uuid.uuid4()
    result = await handler(user_id=tid, body=_Body(reason="refund", days=7), ctx=ctx, db=db)

    assert result["data"] == {"ok": True, "days": 7}
    assert "audit_id" in result
    row: AdminAuditLog = captured["row"]
    assert row.action == "sub.extend"
    assert row.target_type == "user"
    assert row.target_id == str(tid)
    assert row.args_json["reason"] == "refund"
    assert row.args_json["days"] == 7
    assert row.result_json == {"ok": True, "days": 7}
    assert row.admin_user_id == ctx.user.id
    assert row.ip == "1.2.3.4"
    assert row.correlation_id == "cid1"


@pytest.mark.asyncio
async def test_audit_write_skips_row_on_handler_exception():
    captured = {}

    @audit_write(action="sub.extend", target_type="user")
    async def handler(user_id: uuid.UUID, body: _Body, ctx: AdminContext):
        raise RuntimeError("boom")

    db = AsyncMock()
    db.add = MagicMock(side_effect=lambda row: captured.setdefault("row", row))
    db.rollback = AsyncMock()

    ctx = _ctx(db)
    with pytest.raises(RuntimeError):
        await handler(user_id=uuid.uuid4(), body=_Body(reason="r", days=1), ctx=ctx, db=db)
    assert "row" not in captured
