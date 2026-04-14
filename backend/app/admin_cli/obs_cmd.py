"""Phase 1 observability CLI commands: user inspect/export/impersonate, trace, errors."""
from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

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


# ---------- user group ----------

@click.group("user")
def user_group():
    """User observability & management."""
    pass


@user_group.command("inspect")
@click.argument("target")
@click.option("--since", default="24h")
@click.option("--chats", "chats_mode", type=click.Choice(["recent", "all", "errors"]), default="recent")
@click.option("--session", "session_id", default=None)
@click.option("--last-error", is_flag=True)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def user_inspect(target, since, chats_mode, session_id, last_error, env, as_json):
    if last_error:
        chats_mode = "errors"
    c = _client(env)
    params = {"since": since, "chats": chats_mode}
    if session_id:
        params["session"] = session_id
    path = f"/admin/users/{urllib.parse.quote(target, safe='@')}/inspect"
    try:
        envelope = c.get(path, params=params)
    except AdminClientError as e:
        die(str(e))
    data = envelope.data

    if as_json:
        emit_json(data, audit_id=envelope.audit_id, env=envelope.env)
        return

    u = data["user"]
    emit_table(f"USER  {u['email']}  ({u['id']})", [
        ("created", u["created_at"]),
        ("auth", u.get("auth_provider", "?")),
        ("pets", ", ".join(p["name"] for p in data.get("pets", [])) or "-"),
        ("messages", data["counters"].get("messages_in_window", 0)),
        ("errors", data["counters"].get("errors_in_window", 0)),
    ])
    click.secho("\nActivity:", bold=True)
    for row in data.get("activity", [])[:20]:
        marker = "✗" if row.get("error") else "✓"
        click.echo(f"  {row['ts'][:19]} {marker} {row['role']:5s}  {(row.get('content') or '')[:80]}  cid={row.get('correlation_id') or '-'}")


@user_group.command("export")
@click.argument("target")
@click.option("--reason", required=True)
@click.option("--out", "out_path", default=None)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def user_export(target, reason, out_path, env, as_json):
    c = _client(env)
    try:
        envelope = c.post(f"/admin/users/{urllib.parse.quote(target, safe='@')}/export", {"reason": reason})
    except AdminClientError as e:
        die(str(e))
    bundle = envelope.data
    target_path = Path(out_path) if out_path else Path(f"./export-{target.replace('@','_')}.json")
    target_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, default=str))
    if as_json:
        emit_json({"path": str(target_path), "bytes": target_path.stat().st_size}, audit_id=envelope.audit_id, env=envelope.env)
    else:
        emit_table("Exported", [("path", target_path), ("audit_id", envelope.audit_id)])


@user_group.command("impersonate")
@click.argument("target")
@click.option("--reason", required=True)
@click.option("--ttl", "ttl_minutes", default=10, type=int)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def user_impersonate(target, reason, ttl_minutes, env, as_json):
    c = _client(env)
    try:
        envelope = c.post(
            f"/admin/users/{urllib.parse.quote(target, safe='@')}/impersonate",
            {"reason": reason, "ttl_minutes": ttl_minutes},
        )
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, audit_id=envelope.audit_id, env=envelope.env)
    else:
        emit_table("Impersonation token", [
            ("token", envelope.data["token"]),
            ("expires_in", f"{envelope.data['expires_in']}s"),
            ("audit_id", envelope.audit_id),
        ])


# ---------- trace ----------

@click.command("trace")
@click.argument("correlation_id")
@click.option("--show-tools", is_flag=True)
@click.option("--show-system-prompt", is_flag=True)
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def trace_cmd(correlation_id, show_tools, show_system_prompt, env, as_json):
    c = _client(env)
    params = {"show_tools": show_tools, "show_system_prompt": show_system_prompt}
    try:
        envelope = c.get(f"/admin/traces/{correlation_id}", params=params)
    except AdminClientError as e:
        die(str(e))
    data = envelope.data
    if as_json:
        emit_json(data, audit_id=envelope.audit_id, env=envelope.env)
        return
    click.secho(f"TRACE {data['correlation_id']}", bold=True)
    req = data.get("chat_request") or {}
    click.echo(f"  user message: {(req.get('message') or '')[:120]}")
    for r in data.get("rounds", []):
        click.secho(f"  Round {r['round']}", underline=True)
        resp = r.get("llm_response") or {}
        click.echo(f"    model={(r.get('llm_request') or {}).get('model','?')}  tokens={resp.get('prompt_tokens','?')}/{resp.get('completion_tokens','?')}")
        if resp.get("content"):
            click.echo(f"    content: {resp['content'][:200]}")
        for tc in r.get("tool_calls", []):
            call = tc.get("call") or {}
            result = tc.get("result") or {}
            click.echo(f"    → {call.get('tool_name')}({str(call.get('arguments', ''))[:100]}) → success={result.get('success')}")
    if data.get("error"):
        click.secho("  ERROR:", fg="red")
        click.echo(f"    {data['error']}")


# ---------- errors ----------

@click.group("errors")
def errors_group():
    """Recent/historical errors."""
    pass


@errors_group.command("recent")
@click.option("--since", default="24h")
@click.option("--module", default=None)
@click.option("--user", "user_filter", default=None)
@click.option("--group-by", type=click.Choice(["module", "user"]), default="module")
@click.option("--env", type=click.Choice(["prod", "dev"]), default=None)
@click.option("--json", "as_json", is_flag=True)
def errors_recent_cmd(since, module, user_filter, group_by, env, as_json):
    c = _client(env)
    params = {"since": since, "group_by": group_by}
    if module:
        params["module"] = module
    if user_filter:
        params["user"] = user_filter
    try:
        envelope = c.get("/admin/errors", params=params)
    except AdminClientError as e:
        die(str(e))
    if as_json:
        emit_json(envelope.data, audit_id=envelope.audit_id, env=envelope.env)
    else:
        click.secho("Recent errors", bold=True)
        for g in envelope.data.get("groups", []):
            click.echo(f"  {g['count']:4d}  {g['key']}  last={g.get('last_seen')}  sample={g.get('sample_cid')}")
