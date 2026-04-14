"""Tests for `admin login --dev` / `whoami` / `logout` CLI commands."""
from unittest.mock import patch

from click.testing import CliRunner

from app.admin_cli.config import AdminConfig


def test_login_dev_stores_token(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from app.admin_cli.main import cli

    fake_envelope = type("E", (), {})()
    fake_envelope.data = {"token": "NEWTOK", "scope": "admin", "expires_in": 7200, "email": "r@x.com"}
    fake_envelope.audit_id = None
    fake_envelope.env = "dev"

    with patch("app.admin_cli.auth_cmd.AdminClient") as mc:
        mc.return_value.post.return_value = fake_envelope
        result = CliRunner().invoke(cli, ["login", "--dev", "--email", "r@x.com", "--env", "dev"])

    assert result.exit_code == 0, result.output
    cfg = AdminConfig.load()
    assert cfg.token == "NEWTOK"
    assert cfg.email == "r@x.com"
    assert cfg.default_env == "dev"


def test_whoami_prints_email(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    AdminConfig(token="tok", token_expires_at=9999999999, default_env="dev", email="r@x.com").save()
    from app.admin_cli.main import cli

    fake_env = type("E", (), {})()
    fake_env.data = {"email": "r@x.com", "scope": "admin", "user_id": "u1"}
    fake_env.audit_id = None
    fake_env.env = "dev"

    with patch("app.admin_cli.auth_cmd.AdminClient") as mc:
        mc.return_value.get.return_value = fake_env
        result = CliRunner().invoke(cli, ["whoami", "--json"])

    assert result.exit_code == 0, result.output
    assert "r@x.com" in result.output


def test_logout_clears_token(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    AdminConfig(token="tok", token_expires_at=9999999999, default_env="dev", email="r@x.com").save()
    from app.admin_cli.main import cli

    result = CliRunner().invoke(cli, ["logout"])
    assert result.exit_code == 0
    cfg = AdminConfig.load()
    assert cfg.token is None
