"""`admin sub show / list / grant / extend / revoke / verify`."""
from __future__ import annotations

import urllib.parse

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


@click.group("sub")
def sub_group():
    """Subscription management."""
    pass


def _target_path(target: str) -> str:
    return f"/admin/subscriptions/{urllib.parse.quote(target, safe='@')}"


@sub_group.command("show")
@click.argument("target")
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def sub_show(target, env, as_json):
    c = _client(env)
    try:
        envelope = c.get(_target_path(target))
    except AdminClientError as e:
        die(str(e))
    data = envelope.data
    if as_json:
        emit_json(data, audit_id=envelope.audit_id, env=envelope.env)
    else:
        emit_table(f"SUBSCRIPTION  {data['email']}", [
            ("status", data["status"]),
            ("product_id", data["product_id"] or "-"),
            ("expires_at", data["expires_at"] or "-"),
            ("is_duo", data["is_duo"]),
            ("family_role", data.get("family_role") or "-"),
        ])


@sub_group.command("list")
@click.option("--status", default=None)
@click.option("--expired-within", default=None, help="e.g. 7d, 24h")
@click.option("--limit", default=50, type=int)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def sub_list(status, expired_within, limit, env, as_json):
    c = _client(env)
    params = {"limit": limit}
    if status:
        params["status"] = status
    if expired_within:
        params["expired_within"] = expired_within
    try:
        envelope = c.get("/admin/subscriptions", params=params)
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, audit_id=envelope.audit_id, env=envelope.env)
    else:
        click.secho("Subscriptions", bold=True)
        for row in envelope.data:
            click.echo(f"  {row['email']:40s}  {row['status']:8s}  {row.get('product_id') or '-'}")


@sub_group.command("grant")
@click.argument("target")
@click.option("--tier", required=True)
@click.option("--until", required=True, help="ISO date YYYY-MM-DD")
@click.option("--reason", required=True)
@click.option("--product-id", default=None)
@click.option("--force-duo", is_flag=True)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def sub_grant(target, tier, until, reason, product_id, force_duo, env, as_json):
    c = _client(env)
    body = {"reason": reason, "tier": tier, "until": until, "force_duo": force_duo}
    if product_id:
        body["product_id"] = product_id
    try:
        envelope = c.post(f"{_target_path(target)}/grant", body)
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, audit_id=envelope.audit_id, env=envelope.env)
    else:
        emit_table("Granted", [("email", envelope.data["email"]), ("expires_at", envelope.data["expires_at"]), ("audit_id", envelope.audit_id)])


@sub_group.command("extend")
@click.argument("target")
@click.option("--days", required=True, type=int)
@click.option("--reason", required=True)
@click.option("--force-duo", is_flag=True)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def sub_extend(target, days, reason, force_duo, env, as_json):
    c = _client(env)
    body = {"reason": reason, "days": days, "force_duo": force_duo}
    try:
        envelope = c.post(f"{_target_path(target)}/extend", body)
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, audit_id=envelope.audit_id, env=envelope.env)
    else:
        emit_table("Extended", [("email", envelope.data["email"]), ("expires_at", envelope.data["expires_at"]), ("audit_id", envelope.audit_id)])


@sub_group.command("revoke")
@click.argument("target")
@click.option("--reason", required=True)
@click.option("--force-duo", is_flag=True)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def sub_revoke(target, reason, force_duo, env, as_json):
    c = _client(env)
    body = {"reason": reason, "force_duo": force_duo}
    try:
        envelope = c.post(f"{_target_path(target)}/revoke", body)
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, audit_id=envelope.audit_id, env=envelope.env)
    else:
        emit_table("Revoked", [("email", envelope.data["email"]), ("status", envelope.data["status"]), ("audit_id", envelope.audit_id)])


@sub_group.command("verify")
@click.argument("target")
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def sub_verify(target, env, as_json):
    c = _client(env)
    try:
        envelope = c.post(f"{_target_path(target)}/verify", {})
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, env=envelope.env)
    else:
        click.secho("Verify (stub)", bold=True)
        click.echo(envelope.data.get("notes", ""))
