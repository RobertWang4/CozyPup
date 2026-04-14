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


def audit_write(*, action: str, target_type: str | None = None):
    """Decorator that writes an AdminAuditLog row for every successful write.

    Requirements enforced on the wrapped handler:
      * `ctx: AdminContext` and `db: AsyncSession` keyword args are mandatory.
      * The request body (detected as the first Pydantic BaseModel kwarg) must
        expose a non-empty `reason` field, otherwise 422.
      * The audit row is added to the same session as the business change. If
        the handler raises, the row is not added and the caller is responsible
        for rolling back.
    """

    def _decorator(func: Callable[..., Awaitable[Any]]):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            from pydantic import BaseModel  # local import keeps deps.py import-cheap

            ctx: AdminContext | None = kwargs.get("ctx")
            db: AsyncSession | None = kwargs.get("db")
            if ctx is None or db is None:
                raise RuntimeError("audit_write requires ctx and db keyword arguments")

            # Find the request body (first BaseModel kwarg) and validate reason.
            body_obj: BaseModel | None = None
            for v in kwargs.values():
                if isinstance(v, BaseModel):
                    body_obj = v
                    break
            args_json: dict[str, Any] = {}
            if body_obj is not None:
                args_json = body_obj.model_dump(mode="json")
            reason = (args_json.get("reason") or "").strip()
            if not reason:
                raise HTTPException(status_code=422, detail="reason is required for admin writes")

            target_id: str | None = None
            for k in ("user_id", "target_id", "id"):
                if k in kwargs and kwargs[k] is not None:
                    target_id = str(kwargs[k])
                    break

            import inspect
            sig = inspect.signature(func)
            forward_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
            result = await func(*args, **forward_kwargs)

            row = AdminAuditLog(
                admin_user_id=ctx.user.id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                args_json=args_json,
                result_json=result if isinstance(result, dict) else {"value": str(result)},
                ip=ctx.ip,
                correlation_id=ctx.correlation_id,
            )
            db.add(row)
            await db.flush()  # surface FK errors
            await db.commit()  # persist handler mutations + audit row atomically
            return {"data": result, "audit_id": str(row.id), "env": "server"}

        return wrapper

    return _decorator
