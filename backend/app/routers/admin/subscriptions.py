"""Admin subscription writes: show, list, grant, extend, revoke, verify."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User

from .deps import AdminContext, audit_write, require_admin
from .observability import _resolve_user

sub_router = APIRouter(prefix="/subscriptions", tags=["admin-subs"])


def _is_duo(user: User) -> bool:
    return bool(user.subscription_product_id and user.subscription_product_id.endswith(".duo"))


def _sub_summary(user: User) -> dict:
    return {
        "user_id": str(user.id),
        "email": user.email,
        "status": user.subscription_status,
        "product_id": user.subscription_product_id,
        "expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None,
        "is_duo": _is_duo(user),
        "family_role": user.family_role,
        "family_payer_id": str(user.family_payer_id) if user.family_payer_id else None,
    }


class _ExtendBody(BaseModel):
    reason: str
    days: int
    force_duo: bool = False


class _GrantBody(BaseModel):
    reason: str
    tier: str
    until: str
    product_id: str | None = None
    force_duo: bool = False


class _ReasonBody(BaseModel):
    reason: str
    force_duo: bool = False


def _guard_duo(user: User, force_duo: bool) -> None:
    if _is_duo(user) and not force_duo:
        raise HTTPException(
            status_code=409,
            detail="User is on a Duo plan; mutate the payer instead or pass force_duo=true",
        )


@sub_router.get("/{target}")
async def sub_show(
    target: str,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await _resolve_user(db, target)
    return {"data": _sub_summary(user), "audit_id": None, "env": "server"}


@sub_router.get("")
async def sub_list(
    status: str | None = Query(None),
    expired_within: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(User)
    if status:
        q = q.where(User.subscription_status == status)
    if expired_within:
        n = int(expired_within[:-1])
        unit = expired_within[-1]
        delta = {"d": timedelta(days=n), "h": timedelta(hours=n)}[unit]
        cutoff = datetime.now(timezone.utc) - delta
        q = q.where(User.subscription_expires_at >= cutoff, User.subscription_expires_at <= datetime.now(timezone.utc))
    q = q.limit(limit)
    users = (await db.execute(q)).scalars().all()
    return {"data": [_sub_summary(u) for u in users], "audit_id": None, "env": "server"}


@sub_router.post("/{target}/grant")
@audit_write(action="sub.grant", target_type="user")
async def sub_grant(
    target: str,
    body: _GrantBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await _resolve_user(db, target)
    _guard_duo(user, body.force_duo)
    user.subscription_status = "active"
    user.subscription_product_id = body.product_id or f"com.cozypup.{body.tier}_admin_grant"
    user.subscription_expires_at = datetime.fromisoformat(body.until).replace(tzinfo=timezone.utc)
    return _sub_summary(user)


@sub_router.post("/{target}/extend")
@audit_write(action="sub.extend", target_type="user")
async def sub_extend(
    target: str,
    body: _ExtendBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await _resolve_user(db, target)
    _guard_duo(user, body.force_duo)
    base = user.subscription_expires_at or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    user.subscription_expires_at = base + timedelta(days=max(1, int(body.days)))
    if user.subscription_status != "active":
        user.subscription_status = "active"
    return _sub_summary(user)


@sub_router.post("/{target}/revoke")
@audit_write(action="sub.revoke", target_type="user")
async def sub_revoke(
    target: str,
    body: _ReasonBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await _resolve_user(db, target)
    _guard_duo(user, body.force_duo)
    user.subscription_status = "expired"
    user.subscription_expires_at = datetime.now(timezone.utc)
    return _sub_summary(user)


@sub_router.post("/{target}/verify")
async def sub_verify(
    target: str,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Dry-run StoreKit diff. Phase 2 ships this as a stub that returns the DB state;
    Phase 4 wires it to the real StoreKit endpoint."""
    user = await _resolve_user(db, target)
    return {
        "data": {
            "db": _sub_summary(user),
            "storekit": None,
            "match": True,
            "notes": "StoreKit verification not yet wired — returns DB state as a placeholder",
        },
        "audit_id": None,
        "env": "server",
    }
