"""PetPal debug CLI — trace requests, inspect errors, generate tests."""

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
import httpx

from .error_capture import SNAPSHOTS_DIR, ErrorSnapshot, load_snapshot
from .test_generator import generate_test_file


GCP_PROJECT = "cozypup-39487"
TRACE_LOGGER = "cozypup.trace"


@click.group()
def cli():
    """PetPal debug CLI — trace requests, inspect errors, generate tests."""
    pass


# ---------------------------------------------------------------------------
# gcloud helpers
# ---------------------------------------------------------------------------

def _gcloud_read(filter_expr: str, limit: int = 100, order: str = "asc") -> list[dict]:
    """Run gcloud logging read and return parsed JSON entries."""
    cmd = [
        "gcloud", "logging", "read",
        filter_expr,
        f"--project={GCP_PROJECT}",
        "--format=json",
        f"--limit={limit}",
    ]
    if order == "asc":
        cmd.append("--order=asc")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return []
        return json.loads(result.stdout) if result.stdout.strip() else []
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return []


def _parse_trace_entry(entry: dict) -> dict | None:
    """Extract trace fields from a Cloud Logging entry."""
    payload = entry.get("jsonPayload") or {}
    msg = payload.get("message", "")
    try:
        return json.loads(msg)
    except (json.JSONDecodeError, TypeError):
        return None


def _freshness_timestamp(delta: timedelta) -> str:
    """Return ISO timestamp for Cloud Logging freshness filter."""
    return (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# trace — full request chain from Cloud Logging
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("correlation_id")
def trace(correlation_id: str):
    """Show full request trace by correlation ID (from Cloud Logging)."""
    filter_expr = (
        f'jsonPayload.message=~"\\"{correlation_id}\\"" '
        f'AND jsonPayload.logger="{TRACE_LOGGER}"'
    )
    entries = _gcloud_read(filter_expr, limit=50)

    if not entries:
        # Fallback to error snapshots
        try:
            snap = load_snapshot(correlation_id)
        except FileNotFoundError:
            click.echo(f"No trace found for {correlation_id}")
            return
        ts = _format_ts(snap.timestamp)
        user = snap.user_id or snap.correlation_context.get("user_id", "") or "anonymous"
        click.echo(f"Trace for {correlation_id} (error snapshot only)")
        click.echo(f"  Timestamp:  {ts}")
        click.echo(f"  User:       {user}")
        click.echo(f"  Error type: {snap.error_type}")
        click.echo(f"  Message:    {snap.error_message}")
        if snap.traceback:
            click.echo(f"\nTraceback:\n{snap.traceback}")
        return

    parsed = [_parse_trace_entry(e) for e in entries]
    parsed = [p for p in parsed if p]

    if not parsed:
        click.echo(f"No trace entries found for {correlation_id}")
        return

    first = parsed[0]
    click.echo("=" * 60)
    click.echo(f" Trace: {correlation_id}")
    click.echo(f" User:  {first.get('user_id', 'unknown')}")
    click.echo("=" * 60)
    click.echo()

    for i, p in enumerate(parsed, 1):
        log_type = p.get("log_type", "unknown")
        rd = p.get("round")
        data = p.get("data", {})
        round_str = f"  (round {rd})" if rd is not None else ""

        click.echo(f"[{i}] {log_type}{round_str}")

        if log_type == "chat_request":
            click.echo(f"    Message: {data.get('message', '')[:80]}")
            imgs = data.get("image_urls", [])
            if imgs:
                click.echo(f"    Images: {imgs}")
            click.echo(f"    Session: {data.get('session_id', '')}")

        elif log_type == "llm_request":
            click.echo(f"    Model: {data.get('model', '')}")
            click.echo(f"    Messages: {data.get('message_count', '?')} messages")
            for m in data.get("messages_preview", []):
                content = m.get("content", "")[:80]
                click.echo(f"      [{m.get('role')}] {content}")

        elif log_type == "llm_response":
            click.echo(f"    Prompt tokens: {data.get('prompt_tokens', 'N/A')}")
            click.echo(f"    Completion tokens: {data.get('completion_tokens', 'N/A')}")
            tcs = data.get("tool_calls", [])
            if tcs:
                for tc in tcs:
                    click.echo(f"    Tool call: {tc.get('name')}({tc.get('arguments', '')})")
            else:
                preview = data.get("text_preview", "")[:100]
                if preview:
                    click.echo(f"    Text: {preview}")

        elif log_type == "tool_call":
            click.echo(f"    Tool: {data.get('tool_name', '')}")
            click.echo(f"    Arguments: {data.get('arguments', '')}")

        elif log_type == "tool_result":
            click.echo(f"    Tool: {data.get('tool_name', '')}")
            success = data.get("success")
            status = "SUCCESS" if success else "FAILED"
            click.echo(f"    Status: {status}")
            err = data.get("error")
            if err:
                click.echo(f"    Error: {err}")

        elif log_type == "chat_response":
            click.echo(f"    Text: {data.get('final_text', '')[:100]}")
            click.echo(f"    Cards: {data.get('cards', [])}")
            click.echo(f"    Tools: {data.get('tools_called', [])}")
            pt = data.get("total_prompt_tokens")
            ct = data.get("total_completion_tokens")
            if pt is not None or ct is not None:
                click.echo(f"    Total: prompt={pt}  completion={ct}")

        click.echo()


# ---------------------------------------------------------------------------
# requests — recent chat requests for a user
# ---------------------------------------------------------------------------

@cli.command("requests")
@click.option("--user", required=True, help="User ID (prefix match)")
@click.option("--last", default=10, help="Number of recent requests (default: 10)")
def requests_cmd(user: str, last: int):
    """List recent chat requests for a user."""
    filter_expr = (
        f'jsonPayload.message=~"\\"{user}\\"" '
        f'AND jsonPayload.message=~"\\"chat_request\\"" '
        f'AND jsonPayload.logger="{TRACE_LOGGER}"'
    )
    entries = _gcloud_read(filter_expr, limit=last, order="desc")

    if not entries:
        click.echo(f"No requests found for user {user}")
        return

    parsed = [_parse_trace_entry(e) for e in entries]
    parsed = [p for p in parsed if p and p.get("log_type") == "chat_request"]

    if not parsed:
        click.echo(f"No chat_request entries found for user {user}")
        return

    click.echo(f"{'#':<3} {'Correlation ID':<20} {'Message':<50}")
    click.echo("-" * 75)

    for i, p in enumerate(parsed, 1):
        cid = p.get("correlation_id", "")[:18]
        data = p.get("data", {})
        msg = data.get("message", "")[:48]
        click.echo(f"{i:<3} {cid:<20} {msg:<50}")

    click.echo(f"\nTip: Run 'debug trace <correlation_id>' to see full trace")


# ---------------------------------------------------------------------------
# tokens — token usage summary
# ---------------------------------------------------------------------------

@cli.command("tokens")
@click.option("--user", default=None, help="User ID (prefix match, omit for all users)")
@click.option("--period", default="7d", help="Time window: 1d, 7d, 30d (default: 7d)")
def tokens(user: str | None, period: str):
    """Show token usage summary."""
    delta = _parse_since(period)
    if delta is None:
        click.echo(f"Invalid period: {period}. Use 1h, 1d, 7d, 30d etc.")
        return

    filter_expr = (
        f'jsonPayload.message=~"\\"chat_response\\"" '
        f'AND jsonPayload.logger="{TRACE_LOGGER}" '
        f'AND timestamp>="{_freshness_timestamp(delta)}"'
    )
    if user:
        filter_expr += f' AND jsonPayload.message=~"\\"{user}\\""'

    entries = _gcloud_read(filter_expr, limit=1000)

    if not entries:
        click.echo("No usage data found.")
        return

    parsed = [_parse_trace_entry(e) for e in entries]
    parsed = [p for p in parsed if p and p.get("log_type") == "chat_response"]

    if not parsed:
        click.echo("No chat_response entries found.")
        return

    total_requests = len(parsed)

    # Aggregate by model
    by_model: dict[str, dict] = {}
    for p in parsed:
        data = p.get("data", {})
        model = data.get("model", "unknown") or "unknown"
        pt = data.get("total_prompt_tokens") or 0
        ct = data.get("total_completion_tokens") or 0

        if model not in by_model:
            by_model[model] = {"requests": 0, "prompt": 0, "completion": 0}
        by_model[model]["requests"] += 1
        by_model[model]["prompt"] += pt
        by_model[model]["completion"] += ct

    user_label = user[:12] if user else "all users"
    click.echo(f"User: {user_label}")
    click.echo(f"Period: last {period}")
    click.echo(f"Requests: {total_requests}")
    click.echo()
    click.echo(f"{'Model':<45} {'Requests':>8}  {'Prompt':>12}  {'Completion':>12}")
    click.echo("-" * 85)

    total_prompt = 0
    total_completion = 0
    for model, stats in sorted(by_model.items()):
        click.echo(f"{model:<45} {stats['requests']:>8}  {stats['prompt']:>12,}  {stats['completion']:>12,}")
        total_prompt += stats["prompt"]
        total_completion += stats["completion"]

    click.echo("-" * 85)
    click.echo(f"{'Total':<45} {total_requests:>8}  {total_prompt:>12,}  {total_completion:>12,}")


# ---------------------------------------------------------------------------
# Existing error-based commands
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--module", default=None, help="Filter by module path")
@click.option("--user", default=None, help="Filter by user ID (prefix match)")
@click.option("--last", default=10, help="Show last N errors (default: 10)")
def errors(module: str | None, user: str | None, last: int):
    """List recent error snapshots."""
    snapshots = _load_all_snapshots()

    if module:
        snapshots = [s for s in snapshots if module in s.module]

    if user:
        snapshots = [s for s in snapshots if _get_user_id(s).startswith(user)]

    snapshots.sort(key=lambda s: s.timestamp, reverse=True)
    snapshots = snapshots[:last]

    if not snapshots:
        click.echo("No error snapshots found.")
        return

    click.echo("TIMESTAMP            | USER (short) | CATEGORY   | MODULE                  | TYPE            | MESSAGE")
    click.echo("-" * 120)

    for snap in snapshots:
        ts = _format_ts(snap.timestamp)
        uid = _get_user_id(snap)[:8] or "anon"
        msg = snap.error_message[:50]
        click.echo(f"{ts} | {uid:<12} | {snap.category:<10} | {snap.module:<23} | {snap.error_type:<15} | {msg}")


@cli.command("generate-test")
@click.argument("correlation_id")
def generate_test_cmd(correlation_id: str):
    """Generate a pytest from an error snapshot."""
    try:
        snap = load_snapshot(correlation_id)
    except FileNotFoundError:
        click.echo(f"No snapshot found for {correlation_id}")
        return

    path = generate_test_file(snap)
    if path is None:
        click.echo(f"Test already exists for fingerprint {snap.fingerprint}")
    else:
        click.echo(f"Generated test: {path}")


@cli.command()
@click.argument("correlation_id")
@click.option("--url", default="http://localhost:8000", help="Base URL for replay (default: http://localhost:8000)")
def replay(correlation_id: str, url: str):
    """Replay a request using its original data from the snapshot."""
    try:
        snap = load_snapshot(correlation_id)
    except FileNotFoundError:
        click.echo(f"No snapshot found for {correlation_id}")
        return

    request_data = snap.request_data
    method = request_data.get("method", "GET").upper()
    path = request_data.get("path", "/")
    body = request_data.get("body")

    target = url + path
    try:
        with httpx.Client() as client:
            response = client.request(method, target, json=body)
        click.echo(f"Status: {response.status_code}")
        click.echo(response.text)
    except httpx.ConnectError:
        click.echo("Connection failed — is the server running on localhost:8000?")


@cli.command()
@click.option("--since", default="24h", help="Time window: 1h, 24h, 7d (default: 24h)")
def modules(since: str):
    """Show error counts grouped by module — quick health check per module."""
    delta = _parse_since(since)
    if delta is None:
        click.echo(f"Invalid --since value: {since}. Use formats like 1h, 24h, 7d.")
        return

    cutoff = datetime.now(timezone.utc) - delta
    snapshots = _load_all_snapshots()
    snapshots = [s for s in snapshots if _parse_timestamp(s.timestamp) >= cutoff]

    if not snapshots:
        click.echo("No errors in the given time window.")
        return

    # Group by module
    module_groups: dict[str, list[ErrorSnapshot]] = {}
    for snap in snapshots:
        module_groups.setdefault(snap.module, []).append(snap)

    click.echo(f"\nError counts by module (last {since}):\n")
    click.echo(f"{'MODULE':<35} {'COUNT':>5}  {'LAST ERROR':<25} {'LATEST MESSAGE'}")
    click.echo("-" * 110)

    for module, snaps in sorted(module_groups.items(), key=lambda kv: len(kv[1]), reverse=True):
        latest = max(snaps, key=lambda s: s.timestamp)
        last_seen = _format_ts(latest.timestamp)
        msg = latest.error_message[:50]
        click.echo(f"{module:<35} {len(snaps):>5}  {last_seen:<25} {msg}")

    click.echo(f"\nTotal: {len(snapshots)} errors across {len(module_groups)} modules")


@cli.command()
@click.option("--since", default="24h", help="Time window: 1h, 24h, 7d (default: 24h)")
def summary(since: str):
    """Show error summary grouped by fingerprint."""
    delta = _parse_since(since)
    if delta is None:
        click.echo(f"Invalid --since value: {since}. Use formats like 1h, 24h, 7d.")
        return

    cutoff = datetime.now(timezone.utc) - delta
    snapshots = _load_all_snapshots()
    snapshots = [s for s in snapshots if _parse_timestamp(s.timestamp) >= cutoff]

    if not snapshots:
        click.echo("No errors in the given time window.")
        return

    click.echo("FP       | COUNT | CATEGORY   | MODULE                  | LAST SEEN           | MESSAGE")
    click.echo("-" * 80)

    groups: dict[str, list[ErrorSnapshot]] = {}
    for snap in snapshots:
        groups.setdefault(snap.fingerprint, []).append(snap)

    for fp, snaps in sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True):
        latest = max(snaps, key=lambda s: s.timestamp)
        last_seen = _format_ts(latest.timestamp)
        msg = latest.error_message[:60]
        click.echo(
            f"{fp[:8]} | {len(snaps)} | {latest.category} | {latest.module} | {last_seen} | {msg}"
        )


@cli.command()
@click.argument("user_id")
@click.option("--last", default=20, help="Show last N errors (default: 20)")
def user(user_id: str, last: int):
    """Show all errors for a specific user (prefix match on user ID)."""
    snapshots = _load_all_snapshots()
    snapshots = [s for s in snapshots if _get_user_id(s).startswith(user_id)]
    snapshots.sort(key=lambda s: s.timestamp, reverse=True)
    snapshots = snapshots[:last]

    if not snapshots:
        click.echo(f"No errors found for user {user_id}")
        return

    full_uid = _get_user_id(snapshots[0])
    click.echo(f"\nErrors for user: {full_uid}")
    click.echo(f"Total: {len(snapshots)} (showing last {last})\n")

    for snap in snapshots:
        ts = _format_ts(snap.timestamp)
        click.echo(f"  [{ts}] {snap.category}/{snap.error_type}")
        click.echo(f"    {snap.error_message[:80]}")
        click.echo(f"    → {snap.request_data.get('method', '?')} {snap.request_data.get('path', '?')}")
        click.echo(f"    trace: {snap.correlation_id}")
        click.echo()


@cli.command()
@click.option("--since", default="24h", help="Time window: 1h, 24h, 7d (default: 24h)")
def users(since: str):
    """Show error counts grouped by user — find who's having problems."""
    delta = _parse_since(since)
    if delta is None:
        click.echo(f"Invalid --since value: {since}. Use formats like 1h, 24h, 7d.")
        return

    cutoff = datetime.now(timezone.utc) - delta
    snapshots = _load_all_snapshots()
    snapshots = [s for s in snapshots if _parse_timestamp(s.timestamp) >= cutoff]

    if not snapshots:
        click.echo("No errors in the given time window.")
        return

    user_groups: dict[str, list[ErrorSnapshot]] = {}
    for snap in snapshots:
        uid = _get_user_id(snap) or "anonymous"
        user_groups.setdefault(uid, []).append(snap)

    click.echo(f"\nError counts by user (last {since}):\n")
    click.echo(f"{'USER ID':<40} {'COUNT':>5}  {'LAST ERROR':<20} {'LATEST MESSAGE'}")
    click.echo("-" * 110)

    for uid, snaps in sorted(user_groups.items(), key=lambda kv: len(kv[1]), reverse=True):
        latest = max(snaps, key=lambda s: s.timestamp)
        last_seen = _format_ts(latest.timestamp)
        msg = latest.error_message[:40]
        click.echo(f"{uid:<40} {len(snaps):>5}  {last_seen:<20} {msg}")

    click.echo(f"\nTotal: {len(snapshots)} errors across {len(user_groups)} users")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user_id(snap: ErrorSnapshot) -> str:
    """Extract user_id from snapshot, checking both top-level and correlation_context."""
    return snap.user_id or snap.correlation_context.get("user_id", "") or ""


def _load_all_snapshots() -> list[ErrorSnapshot]:
    """Load all valid snapshots from SNAPSHOTS_DIR."""
    snapshots = []
    if not SNAPSHOTS_DIR.exists():
        return snapshots
    for path in SNAPSHOTS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            snapshots.append(ErrorSnapshot(**data))
        except (json.JSONDecodeError, TypeError, KeyError):
            continue
    return snapshots


def _format_ts(ts: str) -> str:
    """Format an ISO timestamp to human-readable form."""
    try:
        return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts


def _parse_timestamp(ts: str) -> datetime:
    """Parse an ISO timestamp, ensuring it's timezone-aware."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_since(since: str) -> timedelta | None:
    """Parse a duration string like '1h', '24h', '7d' into a timedelta."""
    match = re.fullmatch(r"(\d+)([hd])", since)
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == "h":
        return timedelta(hours=value)
    elif unit == "d":
        return timedelta(days=value)
    return None
