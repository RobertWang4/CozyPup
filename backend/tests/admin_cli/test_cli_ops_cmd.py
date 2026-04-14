"""Unit tests for admin ops CLI commands."""
import json
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


def test_ops_ratelimit_clear(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.ops_cmd.AdminClient") as mc:
        mc.return_value.post.return_value = _env({"cleared": 1, "user_key": "alice", "all": False})
        r = CliRunner().invoke(cli, ["ops", "ratelimit", "clear", "--user", "alice", "--reason", "smoke", "--json"])
    assert r.exit_code == 0, r.output


def test_ops_ratelimit_clear_all(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.ops_cmd.AdminClient") as mc:
        mc.return_value.post.return_value = _env({"cleared": 12, "user_key": None, "all": True})
        r = CliRunner().invoke(cli, ["ops", "ratelimit", "clear", "--all", "--reason", "smoke", "--json"])
    assert r.exit_code == 0


def test_ops_flags_set_parses_json_value(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    captured = {}
    def _post(path, body):
        captured["body"] = body
        return _env({"key": body["key"], "value": body["value"]})
    with patch("app.admin_cli.ops_cmd.AdminClient") as mc:
        mc.return_value.post.side_effect = _post
        r = CliRunner().invoke(cli, ["ops", "flags", "set", "auth_dev_enabled", "false", "--reason", "kill dev auth", "--json"])
    assert r.exit_code == 0, r.output
    assert captured["body"]["value"] is False


def test_ops_flags_get(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.ops_cmd.AdminClient") as mc:
        mc.return_value.get.return_value = _env({"key": "auth_dev_enabled", "value": False})
        r = CliRunner().invoke(cli, ["ops", "flags", "get", "auth_dev_enabled", "--json"])
    assert r.exit_code == 0
    assert "auth_dev_enabled" in r.output


def test_ops_session_revoke(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.ops_cmd.AdminClient") as mc:
        mc.return_value.post.return_value = _env({"user_id": "u1", "revoked_at": "t"})
        r = CliRunner().invoke(cli, ["ops", "session", "revoke", "alice@x.com", "--reason", "stolen", "--json"])
    assert r.exit_code == 0
