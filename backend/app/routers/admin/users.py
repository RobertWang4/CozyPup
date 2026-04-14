"""Admin user management writes: search, ban, unban, delete, grant-admin."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User

from .deps import AdminContext, audit_write, require_admin
from .observability import _resolve_user  # reuse the Phase 1 resolver

users_router = APIRouter(prefix="/users", tags=["admin-users"])


class _BanBody(BaseModel):
    reason: str
    days: int = 7


class _ReasonBody(BaseModel):
    reason: str


async def search_users(*, q: str, limit: int, db: AsyncSession) -> list[dict]:
    pattern = f"%{q}%"
    rows = (
        await db.execute(
            select(User)
            .where(or_(User.email.ilike(pattern), User.name.ilike(pattern)))
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "is_admin": bool(u.is_admin),
            "banned_until": u.banned_until.isoformat() if u.banned_until else None,
            "deleted_at": u.deleted_at.isoformat() if u.deleted_at else None,
        }
        for u in rows
    ]


@users_router.get("/search")
async def users_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    results = await search_users(q=q, limit=limit, db=db)
    return {"data": results, "audit_id": None, "env": "server"}


@users_router.post("/{target}/ban")
@audit_write(action="user.ban", target_type="user")
async def users_ban(
    target: str,
    body: _BanBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await _resolve_user(db, target)
    user.banned_until = datetime.now(timezone.utc) + timedelta(days=max(1, int(body.days)))
    return {
        "user_id": str(user.id),
        "email": user.email,
        "banned_until": user.banned_until.isoformat(),
    }


@users_router.post("/{target}/unban")
@audit_write(action="user.unban", target_type="user")
async def users_unban(
    target: str,
    body: _ReasonBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await _resolve_user(db, target)
    user.banned_until = None
    return {"user_id": str(user.id), "email": user.email, "banned_until": None}


@users_router.post("/{target}/delete")
@audit_write(action="user.delete", target_type="user")
async def users_delete(
    target: str,
    body: _ReasonBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await _resolve_user(db, target)
    if user.subscription_status == "active" and user.subscription_product_id:
        raise HTTPException(status_code=409, detail="User has active paid subscription; revoke first")
    user.deleted_at = datetime.now(timezone.utc)
    user.email = f"deleted-{user.id}@deleted.cozypup.local"
    user.name = None
    user.avatar_url = ""
    return {"user_id": str(user.id), "soft_deleted_at": user.deleted_at.isoformat()}


@users_router.post("/{target}/grant-admin")
@audit_write(action="user.grant_admin", target_type="user")
async def users_grant_admin(
    target: str,
    body: _ReasonBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await _resolve_user(db, target)
    user.is_admin = True
    return {"user_id": str(user.id), "email": user.email, "is_admin": True}


@users_router.post("/{target}/revoke-admin")
@audit_write(action="user.revoke_admin", target_type="user")
async def users_revoke_admin(
    target: str,
    body: _ReasonBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await _resolve_user(db, target)
    user.is_admin = False
    return {"user_id": str(user.id), "email": user.email, "is_admin": False}
