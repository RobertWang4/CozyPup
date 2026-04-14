"""Tests for ~/.cozypup/admin.json reader/writer."""
import json
import os
import stat
from pathlib import Path

import pytest

from app.admin_cli.config import AdminConfig


def test_default_path_is_home_cozypup(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = AdminConfig.default_path()
    assert cfg == tmp_path / ".cozypup" / "admin.json"


def test_load_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = AdminConfig.load()
    assert cfg.token is None
    assert cfg.default_env == "prod"


def test_save_writes_0600_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = AdminConfig(token="abc", token_expires_at=1234567890, default_env="dev", email="r@x.com")
    cfg.save()
    path = AdminConfig.default_path()
    assert path.exists()
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
    data = json.loads(path.read_text())
    assert data["token"] == "abc"
    assert data["default_env"] == "dev"


def test_load_rejects_world_readable_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / ".cozypup" / "admin.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"token": "x", "default_env": "prod"}))
    os.chmod(path, 0o644)
    with pytest.raises(PermissionError):
        AdminConfig.load()


def test_clear_token_removes_auth_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = AdminConfig(token="abc", token_expires_at=1, default_env="prod", email="r@x.com")
    cfg.save()
    cfg2 = AdminConfig.load()
    cfg2.clear_token()
    cfg2.save()
    cfg3 = AdminConfig.load()
    assert cfg3.token is None
    assert cfg3.email is None
