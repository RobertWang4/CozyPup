"""Verifies the old debug commands are reachable under `admin debug *`."""
from click.testing import CliRunner

from app.admin_cli.main import cli


def test_admin_debug_help_lists_legacy_commands():
    result = CliRunner().invoke(cli, ["debug", "--help"])
    assert result.exit_code == 0
    # Spot-check that all legacy verbs show up.
    for name in ["lookup", "trace", "requests", "tokens", "errors", "modules", "summary", "replay", "generate-test"]:
        assert name in result.output, f"missing: {name}"
