"""`admin audit list / show / prune`."""
from __future__ import annotations

import click

from .client import AdminClient, AdminClientError
from .config import AdminConfig
from .output import die, emit_json, emit_table


def _client(env: str | None) -> AdminClient:
    try:
        cfg = AdminConfig.load()
    except PermissionError as e:
        die(str(e))
    if not cfg.token:
        die("not logged in; run `admin login --dev --email <you>`")
    return AdminClient(cfg, env=env)


@click.group("audit")
def audit_group():
    """Admin audit log queries."""
    pass


@audit_group.command("list")
@click.option("--since", default="24h")
@click.option("--admin", default=None)
@click.option("--target-user", default=None)
@click.option("--action", default=None)
@click.option("--limit", default=50, type=int)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def audit_list_cmd(since, admin, target_user, action, limit, env, as_json):
    c = _client(env)
    params = {"since": since, "limit": limit}
    if admin: params["admin"] = admin
    if target_user: params["target_user"] = target_user
    if action: params["action"] = action
    try:
        envelope = c.get("/admin/audit", params=params)
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, env=envelope.env)
    else:
        click.secho(f"Audit log (since {since})", bold=True)
        for row in envelope.data:
            click.echo(f"  {row['created_at'][:19]}  {row['action']:20s}  target={row.get('target_id') or '-'}  reason={row.get('args_json', {}).get('reason', '-')}")


@audit_group.command("show")
@click.argument("audit_id")
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def audit_show_cmd(audit_id, env, as_json):
    c = _client(env)
    try:
        envelope = c.get(f"/admin/audit/{audit_id}")
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, env=envelope.env)
    else:
        emit_table(f"Audit {audit_id}", [
            ("action", envelope.data.get("action")),
            ("admin", envelope.data.get("admin_user_id")),
            ("target", envelope.data.get("target_id")),
            ("created_at", envelope.data.get("created_at")),
            ("args", envelope.data.get("args_json")),
        ])


@audit_group.command("prune")
@click.option("--before", required=True, help="e.g. 90d")
@click.option("--reason", required=True)
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def audit_prune_cmd(before, reason, yes, env, as_json):
    if not yes:
        click.confirm(f"Really prune audit rows older than {before}?", abort=True)
    c = _client(env)
    try:
        envelope = c.post("/admin/audit/prune", {"reason": reason, "before": before})
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, audit_id=envelope.audit_id, env=envelope.env)
    else:
        emit_table("Pruned", [("deleted", envelope.data.get("deleted")), ("before", envelope.data.get("before")), ("audit_id", envelope.audit_id)])
