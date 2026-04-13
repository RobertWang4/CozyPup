"""Click root for the admin CLI."""
from __future__ import annotations

import sys

import click

from .auth_cmd import config_group, login_cmd, logout_cmd, ping_cmd, whoami_cmd


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


@cli.group("debug")
def debug_group():
    """Wrappers for the legacy debug commands (populated by Task A10)."""
    pass


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
