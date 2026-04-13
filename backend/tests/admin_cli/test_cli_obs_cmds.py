"""Unit tests for the Phase 1 observability CLI commands."""
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from app.admin_cli.config import AdminConfig
from app.admin_cli.main import cli


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    AdminConfig(token="tok", token_expires_at=9999999999, default_env="dev", email="r@x.com").save()


def _fake_envelope(data):
    e = MagicMock()
    e.data = data
    e.audit_id = "a1"
    e.env = "dev"
    return e


def test_user_inspect_json_prints_activity(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    payload = {
        "user": {"id": "u1", "email": "alice@x.com", "created_at": "2026-02-14"},
        "pets": [],
        "counters": {"messages_in_window": 1, "errors_in_window": 0},
        "activity": [{"ts": "2026-04-12T10:02:00Z", "role": "user", "correlation_id": "cid1", "content": "hi", "error": None}],
    }
    with patch("app.admin_cli.obs_cmd.AdminClient") as mc:
        mc.return_value.get.return_value = _fake_envelope(payload)
        r = CliRunner().invoke(cli, ["user", "inspect", "alice@x.com", "--json"])
    assert r.exit_code == 0, r.output
    assert "alice@x.com" in r.output
    assert "cid1" in r.output


def test_trace_json_prints_rounds(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    payload = {"correlation_id": "cid1", "chat_request": {}, "rounds": [{"round": 0, "tool_calls": []}], "chat_response": None, "error": None}
    with patch("app.admin_cli.obs_cmd.AdminClient") as mc:
        mc.return_value.get.return_value = _fake_envelope(payload)
        r = CliRunner().invoke(cli, ["trace", "cid1", "--json"])
    assert r.exit_code == 0, r.output
    assert "cid1" in r.output


def test_errors_recent_json(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    payload = {"groups": [{"key": "m:KeyError", "count": 3, "sample_cid": "cid2", "last_seen": "t"}]}
    with patch("app.admin_cli.obs_cmd.AdminClient") as mc:
        mc.return_value.get.return_value = _fake_envelope(payload)
        r = CliRunner().invoke(cli, ["errors", "recent", "--since", "24h", "--json"])
    assert r.exit_code == 0, r.output
    assert "KeyError" in r.output


def test_user_impersonate_requires_reason(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.obs_cmd.AdminClient") as mc:
        mc.return_value.post.return_value = _fake_envelope({"token": "xx", "scope": "user", "expires_in": 600, "user_id": "u1"})
        r = CliRunner().invoke(cli, ["user", "impersonate", "alice@x.com", "--reason", "repro", "--json"])
    assert r.exit_code == 0, r.output
    assert "xx" in r.output


def test_user_export_writes_bundle(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with patch("app.admin_cli.obs_cmd.AdminClient") as mc:
        mc.return_value.post.return_value = _fake_envelope({"users": [{"id": "u1", "email": "alice@x.com"}], "pets": [], "chats": [], "chat_sessions": [], "calendar_events": [], "reminders": [], "traces": [], "audit": []})
        r = CliRunner().invoke(cli, ["user", "export", "alice@x.com", "--reason", "gdpr", "--json", "--out", str(tmp_path / "out.json")])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "out.json").exists()
