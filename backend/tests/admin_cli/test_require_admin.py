"""Unit tests for require_admin dependency."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth import create_access_token
from app.routers.admin.deps import require_admin


def _cred(tok: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok)


def _db_returning(user) -> AsyncMock:
    db = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = user
    db.execute.return_value = res
    return db


def _user(is_admin: bool):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = "robert@x.com"
    u.is_admin = is_admin
    return u


@pytest.mark.asyncio
async def test_require_admin_accepts_admin_scope_admin_user():
    user = _user(True)
    tok = create_access_token(str(user.id), scope="admin", ttl_minutes=10)
    ctx = await require_admin(credentials=_cred(tok), db=_db_returning(user), request=MagicMock())
    assert ctx.user.id == user.id
    assert ctx.scope == "admin"


@pytest.mark.asyncio
async def test_require_admin_rejects_user_scope_with_404():
    user = _user(True)
    tok = create_access_token(str(user.id))  # default scope=user
    with pytest.raises(HTTPException) as exc:
        await require_admin(credentials=_cred(tok), db=_db_returning(user), request=MagicMock())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_require_admin_rejects_non_admin_user_with_404():
    user = _user(False)
    tok = create_access_token(str(user.id), scope="admin", ttl_minutes=10)
    with pytest.raises(HTTPException) as exc:
        await require_admin(credentials=_cred(tok), db=_db_returning(user), request=MagicMock())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_require_admin_rejects_missing_credentials_with_404():
    with pytest.raises(HTTPException) as exc:
        await require_admin(credentials=None, db=AsyncMock(), request=MagicMock())
    assert exc.value.status_code == 404
