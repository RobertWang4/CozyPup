"""RAG observability aggregates over `ChatAuditLog`.

Read-only — no new tables, no migrations. Surfaces the metrics needed
to spot content gaps (queries where retrieval returned nothing useful),
latency health, and model-mix. Aggregation runs in Python against a
time-bounded SELECT; at audit volumes we care about today (thousands
of rows/day, max), this is comfortably sub-50ms.

The `retrieved_chunks` column is a JSONB list produced by
`chat_audit.extract_retrieved_chunks`, shaped as:

    [{"title": ..., "url": ..., "distance": float | None}, ...]

Zero-recall predicate (evaluated in Python for SQLite-compat in tests):

    len(retrieved_chunks) == 0
    OR min(c["distance"] for c in chunks if distance is not None) > threshold
    OR no chunk carried a usable distance at all
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import ChatAuditLog


def _min_distance(chunks: list[dict] | None) -> float | None:
    """Return the smallest numeric distance in a retrieved_chunks list."""
    if not chunks:
        return None
    vals = [
        c["distance"]
        for c in chunks
        if isinstance(c, dict) and isinstance(c.get("distance"), (int, float))
    ]
    return float(min(vals)) if vals else None


def _is_zero_recall(chunks: list[dict] | None, threshold: float) -> bool:
    """True when the turn's retrieval produced nothing actionable.

    - no chunks at all → zero recall
    - chunks exist but none carry a distance → treat as zero recall
      (we can't prove relevance)
    - min distance exceeds the retrieval threshold → noise-only hit
    """
    if not chunks:
        return True
    md = _min_distance(chunks)
    if md is None:
        return True
    return md > threshold


def _percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    s = sorted(values)
    # Nearest-rank; fine for observability.
    idx = max(0, min(len(s) - 1, int(round(pct / 100.0 * (len(s) - 1)))))
    return int(s[idx])


async def compute_rag_stats(
    days: int = 7,
    zero_recall_limit: int = 50,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Aggregate RAG telemetry over the last `days` days.

    `now` is injectable for deterministic tests.
    """
    days = max(1, int(days))
    zero_recall_limit = max(0, int(zero_recall_limit))
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    threshold = settings.rag_distance_threshold

    async with async_session() as db:
        stmt = (
            select(ChatAuditLog)
            .where(ChatAuditLog.created_at >= since)
            .order_by(ChatAuditLog.created_at.desc())
        )
        rows = (await db.execute(stmt)).scalars().all()

    total_turns = len(rows)
    turns_with_retrieval = 0
    zero_recall_turns = 0
    emergency_route_count = 0
    top1_distances: list[float] = []
    response_times: list[int] = []
    model_counts: dict[str, int] = {}
    zero_recall_queries: list[dict[str, Any]] = []

    for r in rows:
        chunks = r.retrieved_chunks or []
        if chunks:
            turns_with_retrieval += 1
        if _is_zero_recall(chunks, threshold):
            zero_recall_turns += 1
            if len(zero_recall_queries) < zero_recall_limit:
                # raw_query is user-typed content, safe to surface. user_id is
                # intentionally omitted — content-gap review doesn't need it.
                zero_recall_queries.append({
                    "raw_query": r.raw_query,
                    "species": r.species,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "min_distance": _min_distance(chunks),
                })
        md = _min_distance(chunks)
        if md is not None:
            top1_distances.append(md)
        if r.response_time_ms is not None:
            response_times.append(int(r.response_time_ms))
        if r.model_used:
            model_counts[r.model_used] = model_counts.get(r.model_used, 0) + 1
        if r.is_emergency_route:
            emergency_route_count += 1

    avg_top1 = (
        sum(top1_distances) / len(top1_distances) if top1_distances else None
    )
    top_models = sorted(
        ({"model": m, "count": c} for m, c in model_counts.items()),
        key=lambda x: x["count"],
        reverse=True,
    )

    return {
        "window_days": days,
        "since": since.isoformat(),
        "until": now.isoformat(),
        "distance_threshold": threshold,
        "total_turns": total_turns,
        "turns_with_retrieval": turns_with_retrieval,
        "zero_recall_turns": zero_recall_turns,
        "avg_top1_distance": avg_top1,
        "p50_response_time_ms": _percentile(response_times, 50),
        "p95_response_time_ms": _percentile(response_times, 95),
        "emergency_route_count": emergency_route_count,
        "top_models_used": top_models,
        "zero_recall_queries": zero_recall_queries,
    }
