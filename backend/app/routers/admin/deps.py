"""Shared admin-router dependencies: context, auth guard, audit decorator."""
from __future__ import annotations

import functools
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_token
from app.database import get_db
from app.debug.correlation import get_correlation_id, set_user_id
from app.models import AdminAuditLog, User

_admin_security = HTTPBearer(auto_error=False)

# Per spec §4.2: surface 404 to unauth/non-admin to avoid advertising admin routes;
# 401 only for authenticated admins with expired tokens so CLI can re-login.
_HIDE_STATUS = status.HTTP_404_NOT_FOUND
_HIDE_DETAIL = "Not Found"


@dataclass
class AdminContext:
    user: User
    scope: str
    token_iat: int | None
    ip: str | None
    correlation_id: str | None


async def require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_admin_security),
    db: AsyncSession = Depends(get_db),
) -> AdminContext:
    if credentials is None:
        raise HTTPException(status_code=_HIDE_STATUS, detail=_HIDE_DETAIL)

    try:
        payload = verify_token(credentials.credentials, "access")
    except HTTPException as e:
        # Expired token → 401 so the CLI knows to refresh; everything else → 404.
        if e.detail == "Token expired":
            raise
        raise HTTPException(status_code=_HIDE_STATUS, detail=_HIDE_DETAIL)

    if payload.get("scope") != "admin":
        raise HTTPException(status_code=_HIDE_STATUS, detail=_HIDE_DETAIL)

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=_HIDE_STATUS, detail=_HIDE_DETAIL)

    row = await db.execute(select(User).where(User.id == user_id))
    user = row.scalar_one_or_none()
    if user is None or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=_HIDE_STATUS, detail=_HIDE_DETAIL)

    set_user_id(str(user_id))
    ip = None
    if hasattr(request, "client") and request.client is not None:
        ip = request.client.host
    return AdminContext(
        user=user,
        scope="admin",
        token_iat=payload.get("iat"),
        ip=ip,
        correlation_id=get_correlation_id(),
    )
