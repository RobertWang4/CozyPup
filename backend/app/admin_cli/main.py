"""Click root for the admin CLI."""
from __future__ import annotations

import sys

import click

from .audit_cmd import audit_group
from .auth_cmd import config_group, login_cmd, logout_cmd, ping_cmd, whoami_cmd
from .obs_cmd import errors_group, trace_cmd, user_group
from .ops_cmd import ops_group
from .sub_cmd import sub_group


@click.group()
@click.version_option("0.1.0", prog_name="admin")
def cli():
    """CozyPup admin CLI."""
    pass


cli.add_command(login_cmd)
cli.add_command(logout_cmd)
cli.add_command(whoami_cmd)
cli.add_command(ping_cmd)
cli.add_command(config_group)
cli.add_command(user_group)
cli.add_command(trace_cmd)
cli.add_command(errors_group)
cli.add_command(ops_group)
cli.add_command(sub_group)
cli.add_command(audit_group)


@cli.group("debug")
def debug_group():
    """Legacy debug commands (trace, errors, tokens, ...). Rehomed under admin."""
    pass


from .debug_cmd import attach_legacy_debug  # noqa: E402
attach_legacy_debug(debug_group)


def debug_shim():
    """Back-compat entrypoint for the old `debug` script."""
    click.secho(
        "[deprecated] `debug` is now `admin debug`. Forwarding...",
        fg="yellow", err=True,
    )
    args = sys.argv[1:]
    sys.argv = ["admin", "debug", *args]
    cli()


if __name__ == "__main__":
    cli()
