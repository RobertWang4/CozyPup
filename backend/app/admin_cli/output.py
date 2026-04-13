"""Human/JSON output helpers for the admin CLI."""
from __future__ import annotations

import json
import sys
from typing import Any

import click


def emit_json(data: Any, *, audit_id: str | None = None, env: str | None = None) -> None:
    click.echo(json.dumps({"data": data, "audit_id": audit_id, "env": env}, ensure_ascii=False, indent=2, default=str))


def emit_table(title: str, rows: list[tuple[str, Any]]) -> None:
    click.secho(title, bold=True)
    width = max((len(k) for k, _ in rows), default=0)
    for k, v in rows:
        click.echo(f"  {k.ljust(width)}  {v}")


def die(msg: str, code: int = 1) -> None:
    click.secho(msg, fg="red", err=True)
    sys.exit(code)
