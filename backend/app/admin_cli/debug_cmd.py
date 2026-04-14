"""Rehome legacy `debug` click commands under `admin debug *`.

We import the existing click group from app.debug.cli and attach each of its
commands to our own `admin debug` group. This keeps all output, flags, and
behaviour identical — we are only moving the mount point.
"""
from __future__ import annotations

import click

from app.debug.cli import cli as _legacy_cli


def attach_legacy_debug(target_group: click.Group) -> None:
    for name, cmd in _legacy_cli.commands.items():
        target_group.add_command(cmd, name=name)
