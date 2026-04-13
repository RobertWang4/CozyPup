"""Unit tests for admin sub CLI commands."""
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


def test_sub_show_prints_status(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.sub_cmd.AdminClient") as mc:
        mc.return_value.get.return_value = _env({
            "user_id": "u1", "email": "alice@x.com", "status": "active",
            "product_id": "com.cozypup.pro_monthly", "expires_at": "2026-05-01",
            "is_duo": False, "family_role": None, "family_payer_id": None,
        })
        r = CliRunner().invoke(cli, ["sub", "show", "alice@x.com", "--json"])
    assert r.exit_code == 0, r.output
    assert "active" in r.output


def test_sub_extend_requires_reason_and_days(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.sub_cmd.AdminClient") as mc:
        mc.return_value.post.return_value = _env({"user_id": "u1", "email": "alice@x.com", "status": "active", "product_id": "x", "expires_at": "2026-05-31", "is_duo": False, "family_role": None, "family_payer_id": None})
        r = CliRunner().invoke(cli, ["sub", "extend", "alice@x.com", "--days", "30", "--reason", "goodwill", "--json"])
    assert r.exit_code == 0, r.output


def test_sub_revoke_requires_reason(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = CliRunner().invoke(cli, ["sub", "revoke", "alice@x.com", "--json"])
    assert r.exit_code != 0  # missing --reason


def test_sub_list_filter(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.sub_cmd.AdminClient") as mc:
        mc.return_value.get.return_value = _env([{"user_id": "u1", "email": "alice@x.com", "status": "expired"}])
        r = CliRunner().invoke(cli, ["sub", "list", "--status", "expired", "--json"])
    assert r.exit_code == 0
    assert "alice@x.com" in r.output
