"""Export chat traces into one JSONL file per chat session (Claude Code style).

Sources:
  gcs     — the permanent Cloud Logging sink at gs://cozypup-traces (default)
  logging — Cloud Logging directly (last 30 days only, useful before the sink filled up)

Output layout:
  <out>/<user_id>/<session_id>.jsonl   one trace entry per line, time-ordered
  <out>/index.json                     {session_id: {user_id, first_ts, last_ts, requests}}

Usage:
  python scripts/export_traces.py                       # gcs → ./traces
  python scripts/export_traces.py --source logging --since 30d
  python scripts/export_traces.py --user <user_id> --out /tmp/traces
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT = "cozypup-39487"
BUCKET = "gs://cozypup-traces"
TRACE_LOGGER = "cozypup.trace"


def _run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{r.stderr}")
    return r.stdout


def _parse_since(s: str) -> str:
    m = re.fullmatch(r"(\d+)([hd])", s)
    if not m:
        sys.exit("--since must look like 24h or 30d")
    n, unit = int(m.group(1)), m.group(2)
    delta = timedelta(hours=n) if unit == "h" else timedelta(days=n)
    return (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def _entries_from_gcs() -> list[dict]:
    """Every object the sink wrote is newline-delimited LogEntry JSON."""
    paths = _run(["gcloud", "storage", "ls", "-r", f"{BUCKET}/**"]).split()
    entries: list[dict] = []
    for p in paths:
        if not p.endswith(".json"):
            continue
        for line in _run(["gcloud", "storage", "cat", p]).splitlines():
            if line.strip():
                entries.append(json.loads(line))
    return entries


def _entries_from_logging(since: str) -> list[dict]:
    out = _run([
        "gcloud", "logging", "read",
        f'jsonPayload.logger="{TRACE_LOGGER}" AND timestamp>="{since}"',
        f"--project={PROJECT}", "--format=json", "--limit=100000", "--order=asc",
    ])
    return json.loads(out) if out.strip() else []


def _trace_from_entry(entry: dict) -> dict | None:
    msg = (entry.get("jsonPayload") or {}).get("message", "")
    try:
        trace = json.loads(msg)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(trace, dict) or "log_type" not in trace:
        return None
    trace["timestamp"] = entry.get("timestamp")
    return trace


def export(entries: list[dict], out: Path, only_user: str | None) -> dict:
    traces = [t for e in entries if (t := _trace_from_entry(e))]
    traces.sort(key=lambda t: t["timestamp"] or "")

    # correlation_id → session_id comes from the chat_request entry.
    session_of: dict[str, str] = {}
    for t in traces:
        if t["log_type"] == "chat_request":
            sid = (t.get("data") or {}).get("session_id")
            if sid:
                session_of[t["correlation_id"]] = str(sid)

    by_session: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in traces:
        user = t.get("user_id") or "anonymous"
        if only_user and user != only_user:
            continue
        sid = session_of.get(t["correlation_id"], f"orphan-{t['correlation_id']}")
        by_session[(user, sid)].append(t)

    index: dict[str, dict] = {}
    for (user, sid), items in by_session.items():
        path = out / user / f"{sid}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for t in items:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        index[sid] = {
            "user_id": user,
            "first_ts": items[0]["timestamp"],
            "last_ts": items[-1]["timestamp"],
            "requests": len({t["correlation_id"] for t in items}),
        }
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["gcs", "logging"], default="gcs")
    ap.add_argument("--since", default="30d", help="logging source only, e.g. 24h / 30d")
    ap.add_argument("--user", help="only export this user_id")
    ap.add_argument("--out", default="traces", type=Path)
    args = ap.parse_args()

    entries = _entries_from_gcs() if args.source == "gcs" else _entries_from_logging(_parse_since(args.since))
    index = export(entries, args.out, args.user)
    n_req = sum(v["requests"] for v in index.values())
    print(f"{len(entries)} log entries → {len(index)} sessions, {n_req} requests → {args.out}/")


if __name__ == "__main__":
    main()
