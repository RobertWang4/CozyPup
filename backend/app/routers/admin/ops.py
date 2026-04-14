"""Admin ops routes: ratelimit clear, session revoke, feature flags, cache flush."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import flags
from app.database import get_db
from app.middleware import rate_limit
from app.models import FeatureFlag, TokenRevocation, User

from .deps import AdminContext, audit_write, require_admin
from .observability import _resolve_user

ops_router = APIRouter(prefix="/ops", tags=["admin-ops"])


class _RatelimitClearBody(BaseModel):
    reason: str
    user_key: str | None = None
    all: bool = False


class _FlagSetBody(BaseModel):
    reason: str
    key: str
    value: Any
    description: str | None = None


class _FlagUnsetBody(BaseModel):
    reason: str
    key: str


class _SessionRevokeBody(BaseModel):
    reason: str
    target: str


class _CacheFlushBody(BaseModel):
    reason: str
    key: str


@ops_router.post("/ratelimit/clear")
@audit_write(action="ops.ratelimit.clear", target_type="ratelimit")
async def ratelimit_clear(
    body: _RatelimitClearBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.all:
        cleared = rate_limit.clear(None)
    elif body.user_key:
        cleared = rate_limit.clear(body.user_key)
    else:
        raise HTTPException(status_code=422, detail="user_key or all=true required")
    return {"cleared": cleared, "all": body.all, "user_key": body.user_key}


async def _upsert_flag(key: str, value: Any, description: str | None, user_id: uuid.UUID, db: AsyncSession) -> bool:
    stmt = insert(FeatureFlag).values(
        key=key, value=value, description=description, updated_by=user_id,
    ).on_conflict_do_update(
        index_elements=[FeatureFlag.key],
        set_={"value": value, "description": description, "updated_by": user_id, "updated_at": datetime.now(timezone.utc)},
    )
    await db.execute(stmt)
    return True


@ops_router.post("/flags/set")
@audit_write(action="ops.flags.set", target_type="flag")
async def flags_set(
    body: _FlagSetBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await _upsert_flag(body.key, body.value, body.description, ctx.user.id, db)
    flags._set_in_cache(body.key, body.value)
    return {"key": body.key, "value": body.value}


@ops_router.post("/flags/unset")
@audit_write(action="ops.flags.unset", target_type="flag")
async def flags_unset(
    body: _FlagUnsetBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(FeatureFlag).where(FeatureFlag.key == body.key))
    flags._cache.pop(body.key, None)
    return {"key": body.key, "deleted": True}


@ops_router.get("/flags")
async def flags_list(
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(FeatureFlag))).scalars().all()
    data = [
        {"key": r.key, "value": r.value, "description": r.description, "updated_at": r.updated_at.isoformat()}
        for r in rows
    ]
    return {"data": data, "audit_id": None, "env": "server"}


@ops_router.get("/flags/{key}")
async def flags_get(
    key: str,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(FeatureFlag).where(FeatureFlag.key == key))).scalar_one_or_none()
    if row is None:
        return {"data": {"key": key, "value": None, "source": "default"}, "audit_id": None, "env": "server"}
    return {
        "data": {"key": row.key, "value": row.value, "description": row.description, "updated_at": row.updated_at.isoformat()},
        "audit_id": None, "env": "server",
    }


async def _upsert_revocation(user_id: uuid.UUID, reason: str, db: AsyncSession) -> bool:
    stmt = insert(TokenRevocation).values(
        user_id=user_id, revoked_at=datetime.now(timezone.utc), reason=reason,
    ).on_conflict_do_update(
        index_elements=[TokenRevocation.user_id],
        set_={"revoked_at": datetime.now(timezone.utc), "reason": reason},
    )
    await db.execute(stmt)
    return True


@ops_router.post("/session/revoke")
@audit_write(action="ops.session.revoke", target_type="user")
async def session_revoke(
    body: _SessionRevokeBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await _resolve_user(db, body.target)
    await _upsert_revocation(user.id, body.reason, db)
    return {"user_id": str(user.id), "revoked_at": datetime.now(timezone.utc).isoformat()}


@ops_router.post("/cache/flush")
@audit_write(action="ops.cache.flush", target_type="cache")
async def cache_flush(
    body: _CacheFlushBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return {"key": body.key, "stub": True, "notes": "no named cache layer wired yet"}
