"""Ban check in get_current_user_id: rejects banned_until > now()."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth import create_access_token, get_current_user_id


def _cred(tok: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok)


def _db_for(user) -> AsyncMock:
    db = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = user
    db.execute.return_value = res
    return db


def _user(banned_until=None, deleted_at=None):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.banned_until = banned_until
    u.deleted_at = deleted_at
    return u


@pytest.mark.asyncio
async def test_not_banned_passes():
    user = _user()
    tok = create_access_token(str(user.id))
    uid = await get_current_user_id(credentials=_cred(tok), db=_db_for(user))
    assert uid == user.id


@pytest.mark.asyncio
async def test_banned_until_future_rejected_403():
    user = _user(banned_until=datetime.now(timezone.utc) + timedelta(hours=1))
    tok = create_access_token(str(user.id))
    with pytest.raises(HTTPException) as exc:
        await get_current_user_id(credentials=_cred(tok), db=_db_for(user))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_banned_until_past_passes():
    user = _user(banned_until=datetime.now(timezone.utc) - timedelta(minutes=1))
    tok = create_access_token(str(user.id))
    uid = await get_current_user_id(credentials=_cred(tok), db=_db_for(user))
    assert uid == user.id


@pytest.mark.asyncio
async def test_soft_deleted_rejected_403():
    user = _user(deleted_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    tok = create_access_token(str(user.id))
    with pytest.raises(HTTPException) as exc:
        await get_current_user_id(credentials=_cred(tok), db=_db_for(user))
    assert exc.value.status_code == 403
