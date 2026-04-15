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


class TestUploadAvatar:
    @pytest.mark.asyncio
    async def test_upload_rejects_wrong_content_type(self):
        from fastapi import HTTPException
        from app.routers.auth import upload_avatar

        class FakeFile:
            content_type = "application/pdf"
            async def read(self): return b"junk"

        with pytest.raises(HTTPException) as exc:
            await upload_avatar(file=FakeFile(), user_id=uuid.uuid4(), db=AsyncMock())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_rejects_oversize(self):
        from fastapi import HTTPException
        from app.routers.auth import upload_avatar

        class FakeFile:
            content_type = "image/jpeg"
            async def read(self): return b"x" * (5 * 1024 * 1024 + 1)

        with pytest.raises(HTTPException) as exc:
            await upload_avatar(file=FakeFile(), user_id=uuid.uuid4(), db=AsyncMock())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_happy_path_updates_user_and_returns_url(self, monkeypatch):
        from app.routers import auth as auth_router

        user = _make_user(avatar_url="")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user

        db = AsyncMock()
        db.execute.return_value = mock_result
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        monkeypatch.setattr(
            auth_router,
            "gcs_upload_user_avatar",
            lambda uid, data, ct: f"https://storage.googleapis.com/test/users/{uid}/1.jpg",
        )
        from app.config import settings
        monkeypatch.setattr(settings, "gcs_bucket", "test")

        class FakeFile:
            content_type = "image/jpeg"
            async def read(self): return b"x" * 100

        resp = await auth_router.upload_avatar(file=FakeFile(), user_id=user.id, db=db)
        assert resp["avatar_url"].startswith("https://storage.googleapis.com/test/users/")
        assert user.avatar_url == resp["avatar_url"]
        db.commit.assert_awaited_once()
