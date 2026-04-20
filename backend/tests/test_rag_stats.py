"""Aggregation tests for app.services.rag_stats.

Uses an in-memory SQLite engine (per tests/conftest.py JSONB/Vector
compile shims) to round-trip a handful of ChatAuditLog rows. We patch
the service module's `async_session` symbol so compute_rag_stats reads
from the test engine.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import ChatAuditLog, User


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded(session_factory):
    """Insert a representative mix of audit rows and yield the factory."""
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Create the referenced user (FK).
    async with session_factory() as s:
        s.add(User(id=user_id, email="t@example.com", auth_provider="dev"))
        await s.commit()

    rows = [
        # Good retrieval — top-1 well inside threshold.
        dict(
            raw_query="why is my dog vomiting",
            retrieved_chunks=[
                {"title": "Vomiting", "url": "u1", "distance": 0.12},
                {"title": "GI upset", "url": "u2", "distance": 0.31},
            ],
            response_time_ms=400,
            model_used="grok-fast",
            is_emergency_route=False,
        ),
        # Retrieval returned chunks, but all above threshold → zero recall.
        dict(
            raw_query="pet insurance in Ontario",
            retrieved_chunks=[{"title": "x", "url": "y", "distance": 0.82}],
            response_time_ms=600,
            model_used="grok-fast",
            is_emergency_route=False,
        ),
        # No chunks at all → zero recall.
        dict(
            raw_query="can dogs eat durian",
            retrieved_chunks=[],
            response_time_ms=900,
            model_used="grok-fast",
            is_emergency_route=False,
        ),
        # Emergency path, good retrieval.
        dict(
            raw_query="dog ate chocolate",
            retrieved_chunks=[{"title": "Chocolate toxicity", "distance": 0.08}],
            response_time_ms=1200,
            model_used="kimi-emergency",
            is_emergency_route=True,
        ),
        # Outside the 7-day window; should be excluded.
        dict(
            raw_query="old stale query",
            retrieved_chunks=[],
            response_time_ms=100,
            model_used="grok-fast",
            is_emergency_route=False,
            created_at=now - timedelta(days=30),
        ),
    ]

    async with session_factory() as s:
        for r in rows:
            s.add(ChatAuditLog(
                user_id=user_id,
                raw_query=r["raw_query"],
                is_emergency_route=r["is_emergency_route"],
                retrieved_chunks=r["retrieved_chunks"],
                response_time_ms=r["response_time_ms"],
                model_used=r["model_used"],
                created_at=r.get("created_at", now),
            ))
        await s.commit()

    return session_factory, now


def _patch_session(session_factory):
    """Return a cm that swaps `rag_stats.async_session` to use the test factory."""

    @asynccontextmanager
    async def fake_session():
        async with session_factory() as s:
            yield s

    return patch("app.services.rag_stats.async_session", fake_session)


@pytest.mark.asyncio
async def test_compute_rag_stats_aggregates_correctly(seeded):
    session_factory, now = seeded
    from app.services.rag_stats import compute_rag_stats

    with _patch_session(session_factory):
        stats = await compute_rag_stats(days=7, zero_recall_limit=10, now=now)

    # 4 rows in the last 7 days (the 30-day-old row is excluded).
    assert stats["total_turns"] == 4
    assert stats["turns_with_retrieval"] == 3
    # Zero recall = empty chunks + chunks whose min distance > threshold (0.6).
    assert stats["zero_recall_turns"] == 2
    assert stats["emergency_route_count"] == 1
    # Average of 0.12, 0.82, 0.08.
    assert stats["avg_top1_distance"] == pytest.approx((0.12 + 0.82 + 0.08) / 3)
    # p50/p95 come from [400, 600, 900, 1200].
    assert stats["p50_response_time_ms"] in (600, 900)
    assert stats["p95_response_time_ms"] == 1200
    # Model mix.
    models = {m["model"]: m["count"] for m in stats["top_models_used"]}
    assert models == {"grok-fast": 3, "kimi-emergency": 1}


@pytest.mark.asyncio
async def test_zero_recall_queries_surface_correct_rows(seeded):
    session_factory, now = seeded
    from app.services.rag_stats import compute_rag_stats

    with _patch_session(session_factory):
        stats = await compute_rag_stats(days=7, zero_recall_limit=10, now=now)

    queries = [q["raw_query"] for q in stats["zero_recall_queries"]]
    assert "can dogs eat durian" in queries
    assert "pet insurance in Ontario" in queries
    # Good-retrieval rows must not appear.
    assert "why is my dog vomiting" not in queries
    assert "dog ate chocolate" not in queries
    # PII guard: user_id is intentionally omitted from this listing.
    for q in stats["zero_recall_queries"]:
        assert "user_id" not in q


@pytest.mark.asyncio
async def test_zero_recall_limit_is_respected(seeded):
    session_factory, now = seeded
    from app.services.rag_stats import compute_rag_stats

    with _patch_session(session_factory):
        stats = await compute_rag_stats(days=7, zero_recall_limit=1, now=now)

    assert len(stats["zero_recall_queries"]) == 1


@pytest.mark.asyncio
async def test_window_excludes_old_rows(seeded):
    session_factory, now = seeded
    from app.services.rag_stats import compute_rag_stats

    with _patch_session(session_factory):
        stats = await compute_rag_stats(days=90, zero_recall_limit=50, now=now)

    # Widening the window pulls in the 30-day-old stale row.
    assert stats["total_turns"] == 5


def test_admin_endpoint_fails_closed_without_token(monkeypatch):
    """If admin_api_token is unset, the endpoint returns 403 regardless of input."""
    from app.config import settings
    from app.routers.admin_rag import _require_admin_token
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "admin_api_token", None)
    with pytest.raises(HTTPException) as ei:
        _require_admin_token("anything")
    assert ei.value.status_code == 403


def test_admin_endpoint_rejects_wrong_token(monkeypatch):
    from app.config import settings
    from app.routers.admin_rag import _require_admin_token
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "admin_api_token", "secret")
    with pytest.raises(HTTPException):
        _require_admin_token("nope")
    with pytest.raises(HTTPException):
        _require_admin_token(None)
    # Correct token → no raise.
    _require_admin_token("secret")
