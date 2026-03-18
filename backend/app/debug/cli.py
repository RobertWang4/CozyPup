"""PetPal debug CLI — trace requests, inspect errors, generate tests."""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

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
    click.echo(f"Trace for {correlation_id}")
    click.echo(f"  Timestamp:  {ts}")
    click.echo(f"  Category:   {snap.category}")
    click.echo(f"  Module:     {snap.module}")
    click.echo(f"  Error type: {snap.error_type}")
    click.echo(f"  Message:    {snap.error_message}")


@cli.command()
@click.option("--module", default=None, help="Filter by module path")
@click.option("--last", default=10, help="Show last N errors (default: 10)")
def errors(module: str | None, last: int):
    """List recent error snapshots."""
    snapshots = _load_all_snapshots()

    if module:
        snapshots = [s for s in snapshots if module in s.module]

    snapshots.sort(key=lambda s: s.timestamp, reverse=True)
    snapshots = snapshots[:last]

    if not snapshots:
        click.echo("No error snapshots found.")
        return

    for snap in snapshots:
        ts = _format_ts(snap.timestamp)
        msg = snap.error_message[:60]
        fp = snap.fingerprint[:8]
        click.echo(f"{ts} | {snap.category} | {snap.module} | {snap.error_type} | {msg} | {fp}")


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
def replay(correlation_id: str):
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

    import httpx

    url = f"http://localhost:8000{path}"
    try:
        with httpx.Client() as client:
            response = client.request(method, url, json=body)
        click.echo(f"Status: {response.status_code}")
        click.echo(response.text)
    except httpx.ConnectError:
        click.echo("Connection failed — is the server running on localhost:8000?")


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
