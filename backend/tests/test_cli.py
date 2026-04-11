"""Tests for the debug CLI."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from click.testing import CliRunner

from app.debug.cli import cli, _parse_since
from app.debug.error_capture import ErrorSnapshot


def _make_snapshot(**overrides) -> ErrorSnapshot:
    defaults = dict(
        correlation_id="req-cli-001",
        timestamp="2026-01-15T10:30:00+00:00",
        category="unknown",
        module="app.some_module",
        error_type="ValueError",
        error_message="something broke",
        traceback="Traceback ...",
        fingerprint="aabb112233445566",
        request_data={"method": "POST", "path": "/api/pets", "body": {"name": "Buddy"}},
        correlation_context={"correlation_id": "req-cli-001"},
    )
    defaults.update(overrides)
    return ErrorSnapshot(**defaults)


def _write_snapshot(directory: Path, snap: ErrorSnapshot) -> Path:
    """Write a snapshot JSON file to the given directory."""
    from dataclasses import asdict

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{snap.correlation_id}.json"
    path.write_text(json.dumps(asdict(snap), indent=2))
    return path


class TestTrace:
    def test_trace_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.debug.cli.SNAPSHOTS_DIR", tmp_path)
        monkeypatch.setattr("app.debug.error_capture.SNAPSHOTS_DIR", tmp_path)
        snap = _make_snapshot()
        _write_snapshot(tmp_path, snap)

        runner = CliRunner()
        result = runner.invoke(cli, ["trace", "req-cli-001"])
        assert result.exit_code == 0
        assert "req-cli-001" in result.output
        assert "ValueError" in result.output
        assert "something broke" in result.output
        assert "Traceback ..." in result.output
        # Note: request_data (method/path) is not shown in the snapshot-only trace view

    def test_trace_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.debug.cli.SNAPSHOTS_DIR", tmp_path)
        monkeypatch.setattr("app.debug.error_capture.SNAPSHOTS_DIR", tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["trace", "nonexistent"])
        assert result.exit_code == 0
        assert "No trace found" in result.output


class TestErrors:
    def test_lists_errors(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.debug.cli.SNAPSHOTS_DIR", tmp_path)
        snap1 = _make_snapshot(correlation_id="req-001", timestamp="2026-01-15T10:00:00+00:00")
        snap2 = _make_snapshot(
            correlation_id="req-002",
            timestamp="2026-01-15T11:00:00+00:00",
            module="app.other_module",
        )
        _write_snapshot(tmp_path, snap1)
        _write_snapshot(tmp_path, snap2)

        runner = CliRunner()
        result = runner.invoke(cli, ["errors"])
        assert result.exit_code == 0
        assert "req-001" not in result.output  # correlation_id not in output, but data is
        assert "app.some_module" in result.output
        assert "app.other_module" in result.output

    def test_filter_by_module(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.debug.cli.SNAPSHOTS_DIR", tmp_path)
        snap1 = _make_snapshot(correlation_id="req-001", module="app.pets.service")
        snap2 = _make_snapshot(correlation_id="req-002", module="app.auth.login")
        _write_snapshot(tmp_path, snap1)
        _write_snapshot(tmp_path, snap2)

        runner = CliRunner()
        result = runner.invoke(cli, ["errors", "--module", "pets"])
        assert result.exit_code == 0
        assert "app.pets.service" in result.output
        assert "app.auth.login" not in result.output

    def test_last_limit(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.debug.cli.SNAPSHOTS_DIR", tmp_path)
        for i in range(5):
            snap = _make_snapshot(
                correlation_id=f"req-{i:03d}",
                timestamp=f"2026-01-15T{10+i:02d}:00:00+00:00",
                module=f"app.module_{i}",
            )
            _write_snapshot(tmp_path, snap)

        runner = CliRunner()
        result = runner.invoke(cli, ["errors", "--last", "2"])
        assert result.exit_code == 0
        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        # 2 header lines + 2 data lines
        assert len(lines) == 4

    def test_no_snapshots(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.debug.cli.SNAPSHOTS_DIR", tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["errors"])
        assert result.exit_code == 0
        assert "No error snapshots found" in result.output


class TestGenerateTest:
    def test_generates_file(self, tmp_path, monkeypatch):
        snap_dir = tmp_path / "snapshots"
        test_dir = tmp_path / "tests"
        monkeypatch.setattr("app.debug.cli.SNAPSHOTS_DIR", snap_dir)
        monkeypatch.setattr("app.debug.error_capture.SNAPSHOTS_DIR", snap_dir)
        monkeypatch.setattr("app.debug.test_generator.GENERATED_TESTS_DIR", test_dir)

        snap = _make_snapshot()
        _write_snapshot(snap_dir, snap)

        runner = CliRunner()
        result = runner.invoke(cli, ["generate-test", "req-cli-001"])
        assert result.exit_code == 0
        assert "Generated test:" in result.output

        # Verify file was created
        generated = list(test_dir.glob("*.py"))
        assert len(generated) == 1

    def test_deduplication(self, tmp_path, monkeypatch):
        snap_dir = tmp_path / "snapshots"
        test_dir = tmp_path / "tests"
        monkeypatch.setattr("app.debug.cli.SNAPSHOTS_DIR", snap_dir)
        monkeypatch.setattr("app.debug.error_capture.SNAPSHOTS_DIR", snap_dir)
        monkeypatch.setattr("app.debug.test_generator.GENERATED_TESTS_DIR", test_dir)

        snap = _make_snapshot()
        _write_snapshot(snap_dir, snap)

        runner = CliRunner()
        runner.invoke(cli, ["generate-test", "req-cli-001"])
        result = runner.invoke(cli, ["generate-test", "req-cli-001"])
        assert "Test already exists for fingerprint" in result.output

    def test_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.debug.cli.SNAPSHOTS_DIR", tmp_path)
        monkeypatch.setattr("app.debug.error_capture.SNAPSHOTS_DIR", tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["generate-test", "nonexistent"])
        assert result.exit_code == 0
        assert "No snapshot found" in result.output


class TestReplay:
    def test_replay_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.debug.cli.SNAPSHOTS_DIR", tmp_path)
        monkeypatch.setattr("app.debug.error_capture.SNAPSHOTS_DIR", tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["replay", "nonexistent"])
        assert result.exit_code == 0
        assert "No snapshot found" in result.output

    def test_replay_connection_error(self, tmp_path, monkeypatch):
        snap_dir = tmp_path / "snapshots"
        monkeypatch.setattr("app.debug.cli.SNAPSHOTS_DIR", snap_dir)
        monkeypatch.setattr("app.debug.error_capture.SNAPSHOTS_DIR", snap_dir)

        snap = _make_snapshot()
        _write_snapshot(snap_dir, snap)

        def raise_connect_error(*args, **kwargs):
            import httpx
            raise httpx.ConnectError("Connection refused")

        monkeypatch.setattr("httpx.Client.request", raise_connect_error)

        runner = CliRunner()
        result = runner.invoke(cli, ["replay", "req-cli-001"])
        assert result.exit_code == 0
        assert "Connection failed" in result.output


class TestSummary:
    def test_summary_groups_by_fingerprint(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.debug.cli.SNAPSHOTS_DIR", tmp_path)
        now = datetime.now(timezone.utc)

        # Two errors with same fingerprint, one with different
        snap1 = _make_snapshot(
            correlation_id="req-001",
            timestamp=(now - timedelta(hours=1)).isoformat(),
            fingerprint="aaaa111122223333",
        )
        snap2 = _make_snapshot(
            correlation_id="req-002",
            timestamp=(now - timedelta(minutes=30)).isoformat(),
            fingerprint="aaaa111122223333",
        )
        snap3 = _make_snapshot(
            correlation_id="req-003",
            timestamp=(now - timedelta(minutes=10)).isoformat(),
            fingerprint="bbbb444455556666",
        )
        _write_snapshot(tmp_path, snap1)
        _write_snapshot(tmp_path, snap2)
        _write_snapshot(tmp_path, snap3)

        runner = CliRunner()
        result = runner.invoke(cli, ["summary", "--since", "24h"])
        assert result.exit_code == 0
        assert "aaaa1111" in result.output
        assert "bbbb4444" in result.output
        # aaaa has count 2, should appear with "2"
        assert "| 2 |" in result.output
        assert "| 1 |" in result.output

    def test_summary_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.debug.cli.SNAPSHOTS_DIR", tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["summary"])
        assert result.exit_code == 0
        assert "No errors in the given time window" in result.output

    def test_summary_respects_since(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.debug.cli.SNAPSHOTS_DIR", tmp_path)
        now = datetime.now(timezone.utc)

        # One recent, one old
        snap_recent = _make_snapshot(
            correlation_id="req-recent",
            timestamp=(now - timedelta(minutes=30)).isoformat(),
        )
        snap_old = _make_snapshot(
            correlation_id="req-old",
            timestamp=(now - timedelta(hours=25)).isoformat(),
        )
        _write_snapshot(tmp_path, snap_recent)
        _write_snapshot(tmp_path, snap_old)

        runner = CliRunner()
        # Only 1h window — should only include recent
        result = runner.invoke(cli, ["summary", "--since", "1h"])
        assert result.exit_code == 0
        lines = [l for l in result.output.strip().split("\n") if "|" in l]
        # 1 header line + 1 data line
        assert len(lines) == 2


class TestParseSince:
    def test_hours(self):
        assert _parse_since("1h") == timedelta(hours=1)
        assert _parse_since("24h") == timedelta(hours=24)

    def test_days(self):
        assert _parse_since("7d") == timedelta(days=7)

    def test_invalid(self):
        assert _parse_since("abc") is None
        assert _parse_since("10m") is None
        assert _parse_since("") is None
