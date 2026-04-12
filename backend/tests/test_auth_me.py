"""Tests for /auth/me endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import User


def _make_user(name="Alice", email="a@ex.com", provider="google", avatar_url=""):
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = email
    user.name = name
    user.auth_provider = provider
    user.avatar_url = avatar_url
    user.phone_number = None
    return user


class TestGetMe:
    @pytest.mark.asyncio
    async def test_get_me_returns_avatar_url(self):
        from app.routers.auth import me

        user = _make_user(avatar_url="https://storage.googleapis.com/cozypup-avatars/users/abc/1.jpg")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user

        db = AsyncMock()
        db.execute.return_value = mock_result

        resp = await me(user_id=user.id, db=db)
        assert resp.avatar_url == "https://storage.googleapis.com/cozypup-avatars/users/abc/1.jpg"

    @pytest.mark.asyncio
    async def test_get_me_empty_avatar_url_returns_none(self):
        from app.routers.auth import me

        user = _make_user(avatar_url="")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user

        db = AsyncMock()
        db.execute.return_value = mock_result

        resp = await me(user_id=user.id, db=db)
        assert resp.avatar_url is None
