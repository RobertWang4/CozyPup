"""PetPal debug CLI — trace requests, inspect errors, generate tests."""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
import httpx

from .error_capture import SNAPSHOTS_DIR, ErrorSnapshot, load_snapshot
from .test_generator import generate_test_file


@click.group()
def cli():
    """PetPal debug CLI — trace requests, inspect errors, generate tests."""
    pass


@cli.command()
@click.argument("correlation_id")
def trace(correlation_id: str):
    """Show all log events for a request by correlation ID."""
    try:
        snap = load_snapshot(correlation_id)
    except FileNotFoundError:
        click.echo(f"No snapshot found for {correlation_id}")
        return

    ts = _format_ts(snap.timestamp)
    user = snap.user_id or snap.correlation_context.get("user_id", "") or "anonymous"
    click.echo(f"Trace for {correlation_id}")
    click.echo(f"  Timestamp:  {ts}")
    click.echo(f"  User:       {user}")
    click.echo(f"  Category:   {snap.category}")
    click.echo(f"  Module:     {snap.module}")
    click.echo(f"  Error type: {snap.error_type}")
    click.echo(f"  Message:    {snap.error_message}")

    request_data = snap.request_data
    if request_data:
        method = request_data.get("method", "GET").upper()
        path = request_data.get("path", "/")
        body = request_data.get("body")
        click.echo(f"  Request:    {method} {path}")
        click.echo(f"  Body:       {body}")

    if snap.traceback:
        click.echo("")
        click.echo("Traceback:")
        click.echo(snap.traceback)


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
