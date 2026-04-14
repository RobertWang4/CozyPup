"""Admin audit query routes: list, show, prune."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AdminAuditLog, User

from .deps import AdminContext, audit_write, require_admin
from .observability import _since_to_timedelta

audit_router = APIRouter(prefix="/audit", tags=["admin-audit"])


def _row_to_dict(r: AdminAuditLog) -> dict:
    return {
        "id": str(r.id),
        "action": r.action,
        "admin_user_id": str(r.admin_user_id),
        "target_type": r.target_type,
        "target_id": r.target_id,
        "args_json": r.args_json,
        "result_json": r.result_json,
        "ip": r.ip,
        "correlation_id": r.correlation_id,
        "created_at": r.created_at.isoformat(),
    }


async def list_audit(
    *,
    since: str,
    admin_email: str | None,
    target_user: str | None,
    action: str | None,
    limit: int,
    db: AsyncSession,
) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - _since_to_timedelta(since)
    q = select(AdminAuditLog).where(AdminAuditLog.created_at >= cutoff)
    if admin_email:
        admin_uid = (await db.execute(select(User.id).where(User.email == admin_email))).scalar_one_or_none()
        if admin_uid is None:
            return []
        q = q.where(AdminAuditLog.admin_user_id == admin_uid)
    if target_user:
        q = q.where(AdminAuditLog.target_id == target_user)
    if action:
        q = q.where(AdminAuditLog.action == action)
    q = q.order_by(AdminAuditLog.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [_row_to_dict(r) for r in rows]


@audit_router.get("")
async def audit_list(
    since: str = Query("24h"),
    admin: str | None = Query(None, alias="admin"),
    target_user: str | None = Query(None),
    action: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await list_audit(
        since=since, admin_email=admin, target_user=target_user, action=action, limit=limit, db=db,
    )
    return {"data": data, "audit_id": None, "env": "server"}


@audit_router.get("/{audit_id}")
async def audit_show(
    audit_id: str,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        aid = uuid.UUID(audit_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="audit_id not found")
    row = (await db.execute(select(AdminAuditLog).where(AdminAuditLog.id == aid))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="audit_id not found")
    return {"data": _row_to_dict(row), "audit_id": None, "env": "server"}


class _PruneBody(BaseModel):
    reason: str
    before: str  # e.g. "90d"


@audit_router.post("/prune")
@audit_write(action="audit.prune", target_type="audit")
async def audit_prune(
    body: _PruneBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - _since_to_timedelta(body.before)
    result = await db.execute(delete(AdminAuditLog).where(AdminAuditLog.created_at < cutoff))
    return {"deleted": int(result.rowcount or 0), "before": cutoff.isoformat()}
