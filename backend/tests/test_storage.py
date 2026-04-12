"""Tests for GCS storage helpers."""

from unittest.mock import MagicMock, patch

import pytest

from app.storage import upload_avatar, get_avatar_url


class TestUploadAvatar:
    @patch("app.storage._get_bucket")
    def test_upload_writes_blob_and_returns_url(self, mock_get_bucket):
        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_get_bucket.return_value = mock_bucket

        url = upload_avatar("abc-123", b"fake-image-data", "image/jpeg")

        mock_bucket.blob.assert_called_once_with("avatars/abc-123.jpg")
        mock_blob.upload_from_string.assert_called_once_with(
            b"fake-image-data", content_type="image/jpeg"
        )
        assert "abc-123.jpg" in url

    @patch("app.storage._get_bucket")
    def test_upload_handles_png(self, mock_get_bucket):
        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_get_bucket.return_value = mock_bucket

        url = upload_avatar("abc-123", b"fake-png", "image/png")

        mock_bucket.blob.assert_called_once_with("avatars/abc-123.png")


class TestGetAvatarUrl:
    def test_returns_public_url(self):
        url = get_avatar_url("avatars/abc-123.jpg", "cozypup-avatars")
        assert url == "https://storage.googleapis.com/cozypup-avatars/avatars/abc-123.jpg"


class TestUploadUserAvatar:
    def test_user_avatar_blob_path_format(self, monkeypatch):
        from app import storage

        captured = {}

        class FakeBlob:
            def __init__(self, name): self.name = name; self.cache_control = None
            def upload_from_string(self, data, content_type=None):
                captured["data"] = data
                captured["content_type"] = content_type

        class FakeBucket:
            def blob(self, name):
                captured["blob_name"] = name
                return FakeBlob(name)

        class FakeClient:
            def bucket(self, name): return FakeBucket()

        monkeypatch.setattr(storage, "_get_client", lambda: FakeClient())
        monkeypatch.setattr(storage.settings, "gcs_bucket", "test-bucket")

        url = storage.upload_user_avatar("user-123", b"imagebytes", "image/jpeg")

        assert captured["blob_name"].startswith("users/user-123/")
        assert captured["blob_name"].endswith(".jpg")
        assert captured["data"] == b"imagebytes"
        assert url.startswith("https://storage.googleapis.com/test-bucket/users/user-123/")
