"""`admin ops ratelimit / session / flags / cache` commands."""
from __future__ import annotations

import json

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


def _parse_value(raw: str):
    """Parse a CLI-supplied flag value as JSON, falling back to raw string."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


@click.group("ops")
def ops_group():
    """Ops kill switches and feature flags."""
    pass


# ----- ratelimit -----

@ops_group.group("ratelimit")
def _rl_group():
    pass


@_rl_group.command("clear")
@click.option("--user", "user_key", default=None)
@click.option("--all", "all_users", is_flag=True)
@click.option("--reason", required=True)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def rl_clear(user_key, all_users, reason, env, as_json):
    if not user_key and not all_users:
        die("--user or --all required")
    c = _client(env)
    body = {"reason": reason, "all": bool(all_users)}
    if user_key:
        body["user_key"] = user_key
    try:
        envelope = c.post("/admin/ops/ratelimit/clear", body)
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, audit_id=envelope.audit_id, env=envelope.env)
    else:
        emit_table("Ratelimit cleared", [("cleared", envelope.data.get("cleared")), ("audit_id", envelope.audit_id)])


# ----- session -----

@ops_group.group("session")
def _sess_group():
    pass


@_sess_group.command("revoke")
@click.argument("target")
@click.option("--reason", required=True)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def sess_revoke(target, reason, env, as_json):
    c = _client(env)
    try:
        envelope = c.post("/admin/ops/session/revoke", {"reason": reason, "target": target})
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, audit_id=envelope.audit_id, env=envelope.env)
    else:
        emit_table("Session revoked", [("user_id", envelope.data.get("user_id")), ("revoked_at", envelope.data.get("revoked_at")), ("audit_id", envelope.audit_id)])


# ----- flags -----

@ops_group.group("flags")
def _flags_group():
    pass


@_flags_group.command("list")
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def flags_list_cmd(env, as_json):
    c = _client(env)
    try:
        envelope = c.get("/admin/ops/flags")
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, env=envelope.env)
    else:
        click.secho("Feature flags", bold=True)
        for f in envelope.data:
            click.echo(f"  {f['key']:30s}  = {json.dumps(f['value'])}  ({f.get('description') or '-'})")


@_flags_group.command("get")
@click.argument("key")
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def flags_get_cmd(key, env, as_json):
    c = _client(env)
    try:
        envelope = c.get(f"/admin/ops/flags/{key}")
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, env=envelope.env)
    else:
        emit_table(f"Flag {key}", [("value", json.dumps(envelope.data.get("value"))), ("updated_at", envelope.data.get("updated_at"))])


@_flags_group.command("set")
@click.argument("key")
@click.argument("value")
@click.option("--reason", required=True)
@click.option("--description", default=None)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def flags_set_cmd(key, value, reason, description, env, as_json):
    c = _client(env)
    body = {"reason": reason, "key": key, "value": _parse_value(value)}
    if description:
        body["description"] = description
    try:
        envelope = c.post("/admin/ops/flags/set", body)
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, audit_id=envelope.audit_id, env=envelope.env)
    else:
        emit_table("Flag set", [("key", envelope.data.get("key")), ("value", json.dumps(envelope.data.get("value"))), ("audit_id", envelope.audit_id)])


@_flags_group.command("unset")
@click.argument("key")
@click.option("--reason", required=True)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def flags_unset_cmd(key, reason, env, as_json):
    c = _client(env)
    try:
        envelope = c.post("/admin/ops/flags/unset", {"reason": reason, "key": key})
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, audit_id=envelope.audit_id, env=envelope.env)
    else:
        emit_table("Flag unset", [("key", key), ("audit_id", envelope.audit_id)])


# ----- cache (stub) -----

@ops_group.group("cache")
def _cache_group():
    pass


@_cache_group.command("flush")
@click.option("--key", required=True)
@click.option("--reason", required=True)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def cache_flush_cmd(key, reason, env, as_json):
    c = _client(env)
    try:
        envelope = c.post("/admin/ops/cache/flush", {"reason": reason, "key": key})
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, audit_id=envelope.audit_id, env=envelope.env)
    else:
        emit_table("Cache flush (stub)", [("key", key), ("audit_id", envelope.audit_id)])
