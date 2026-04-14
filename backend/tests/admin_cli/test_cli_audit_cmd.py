"""Unit tests for admin audit CLI commands."""
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from app.admin_cli.config import AdminConfig
from app.admin_cli.main import cli


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    AdminConfig(token="tok", token_expires_at=9999999999, default_env="dev", email="r@x.com").save()


def _env(data):
    e = MagicMock(); e.data = data; e.audit_id = None; e.env = "dev"
    return e


def test_audit_list(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.audit_cmd.AdminClient") as mc:
        mc.return_value.get.return_value = _env([
            {"id": "a1", "action": "sub.extend", "target_id": "u1", "args_json": {"reason": "goodwill"}, "created_at": "2026-04-12T10:00:00Z"},
        ])
        r = CliRunner().invoke(cli, ["audit", "list", "--since", "24h", "--json"])
    assert r.exit_code == 0
    assert "sub.extend" in r.output


def test_audit_show(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.audit_cmd.AdminClient") as mc:
        mc.return_value.get.return_value = _env({"id": "a1", "action": "sub.extend", "args_json": {"reason": "goodwill"}, "created_at": "t"})
        r = CliRunner().invoke(cli, ["audit", "show", "a1", "--json"])
    assert r.exit_code == 0
    assert "sub.extend" in r.output


def test_audit_prune_requires_reason(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = CliRunner().invoke(cli, ["audit", "prune", "--before", "90d"])
    assert r.exit_code != 0  # missing --reason
