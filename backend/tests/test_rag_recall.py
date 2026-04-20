"""RAG retrieval regression guard.

Opt-in — marked `rag_eval` and skipped by default (see `tests/conftest.py`).
Invoke with:

    pytest -m rag_eval -v

Runs the same code path as `python -m knowledge.eval.run_eval` for both
the Chinese and English query sets, then asserts that current results have
not regressed vs the locked-in baseline in `knowledge/eval/baseline.json`.

The eval hits the real Postgres (pgvector) + litellm embedding endpoint —
there is no mocking here by design. If the DB or embedding endpoint is
unreachable, these tests will error out, which is the intended signal.
"""

import json
from pathlib import Path

import pytest

from app.database import engine as _db_engine
from knowledge.eval import run_eval

BASELINE_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "eval" / "baseline.json"
QUERIES_DIR = Path(__file__).resolve().parents[1] / "knowledge" / "eval"


def _load_baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


async def _run_for(queries_file: str, top_n: int) -> dict:
    """Invoke run_eval.run against a specific queries file and return summary counts.

    pytest-asyncio gives each test its own event loop, but the SQLAlchemy async
    engine in `app.database` is module-scoped and caches connections bound to
    whichever loop first touched it. Dispose the engine before running so the
    next test's fresh loop doesn't inherit dead asyncpg connections.
    """
    await _db_engine.dispose()
    # run_eval reads its queries from a module-level path; swap it for the duration
    # of this call so we hit the requested file without touching the CLI.
    original = run_eval.QUERIES_PATH
    run_eval.QUERIES_PATH = QUERIES_DIR / queries_file
    try:
        result = await run_eval.run(top_n=top_n, label=None)
    finally:
        run_eval.QUERIES_PATH = original
    return result["summary"]


def _assert_no_regression(current: dict, baseline: dict, lang: str) -> None:
    # Totals must match — if someone changed the query set, they need to
    # regenerate the baseline deliberately, not silently drift.
    for key in ("positive_total", "negative_total", "emergency_total"):
        assert current[key] == baseline[key], (
            f"[{lang}] {key} changed: current={current[key]} baseline={baseline[key]}. "
            f"Regenerate knowledge/eval/baseline.json if the query set intentionally changed."
        )

    # No regression on the pass counts we care about (tolerance = 0).
    for key in ("positive_topN", "negative_pass", "emergency_pass"):
        assert current[key] >= baseline[key], (
            f"[{lang}] REGRESSION in {key}: current={current[key]} < baseline={baseline[key]}"
        )


@pytest.mark.rag_eval
@pytest.mark.asyncio
async def test_rag_recall_zh_no_regression():
    baseline = _load_baseline()
    summary = await _run_for("queries.json", top_n=baseline["top_n"])
    _assert_no_regression(summary, baseline["zh"], "zh")


@pytest.mark.rag_eval
@pytest.mark.asyncio
async def test_rag_recall_en_no_regression():
    baseline = _load_baseline()
    summary = await _run_for("queries_en.json", top_n=baseline["top_n"])
    _assert_no_regression(summary, baseline["en"], "en")
