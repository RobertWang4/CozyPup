"""Unit tests for user ban/unban/delete/search/grant-admin CLI."""
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from app.admin_cli.config import AdminConfig
from app.admin_cli.main import cli


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    AdminConfig(token="tok", token_expires_at=9999999999, default_env="dev", email="r@x.com").save()


def _env(data):
    e = MagicMock(); e.data = data; e.audit_id = "a1"; e.env = "dev"
    return e


def test_user_ban_requires_reason(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = CliRunner().invoke(cli, ["user", "ban", "alice@x.com", "--days", "7"])
    assert r.exit_code != 0  # missing --reason


def test_user_ban_happy_path(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.obs_cmd.AdminClient") as mc:
        mc.return_value.post.return_value = _env({"email": "alice@x.com", "banned_until": "2026-05-01T00:00:00Z"})
        r = CliRunner().invoke(cli, ["user", "ban", "alice@x.com", "--days", "7", "--reason", "spam", "--json"])
    assert r.exit_code == 0, r.output
    assert "alice@x.com" in r.output


def test_user_unban(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.obs_cmd.AdminClient") as mc:
        mc.return_value.post.return_value = _env({"email": "alice@x.com", "banned_until": None})
        r = CliRunner().invoke(cli, ["user", "unban", "alice@x.com", "--reason", "appeal", "--json"])
    assert r.exit_code == 0


def test_user_delete(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.obs_cmd.AdminClient") as mc:
        mc.return_value.post.return_value = _env({"soft_deleted_at": "2026-04-12T10:00:00Z"})
        r = CliRunner().invoke(cli, ["user", "delete", "alice@x.com", "--reason", "user request", "--json"])
    assert r.exit_code == 0


def test_user_grant_admin(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.obs_cmd.AdminClient") as mc:
        mc.return_value.post.return_value = _env({"email": "alice@x.com", "is_admin": True})
        r = CliRunner().invoke(cli, ["user", "grant-admin", "alice@x.com", "--reason", "bootstrap", "--json"])
    assert r.exit_code == 0
    assert "alice@x.com" in r.output


def test_user_search(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.obs_cmd.AdminClient") as mc:
        mc.return_value.get.return_value = _env([{"id": "u1", "email": "alice@x.com", "name": "Alice", "is_admin": False}])
        r = CliRunner().invoke(cli, ["user", "search", "alice", "--json"])
    assert r.exit_code == 0
    assert "alice@x.com" in r.output
