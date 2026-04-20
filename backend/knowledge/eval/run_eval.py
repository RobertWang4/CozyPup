"""RAG retrieval eval against the knowledge_articles / embeddings tables.

Usage:
    cd backend
    python -m knowledge.eval.run_eval                       # full report
    python -m knowledge.eval.run_eval --top 5               # top-5 hit rate
    python -m knowledge.eval.run_eval --label v1 > eval_v1.txt  # save snapshot

Reads knowledge/eval/queries.json (list of {query, expect_title_any}), embeds
each query, fetches top-N knowledge-base chunks by cosine distance, and checks
whether any top-N chunk's title contains any expected keyword.

The point is a quick before/after signal for chunker + alias changes, not a
formal benchmark. Keep the query set small enough to read the full output.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

# Make imports work when run from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import litellm

from app.config import settings
from app.database import async_session
from app.models import Embedding, SourceType


async def embed_text(text: str) -> list[float]:
    """Inline embedder to avoid a circular import chain through app.agents.

    app.rag.embeddings lazy-imports app.agents for routing kwargs; app.agents
    → tools → knowledge → app.rag.retrieval → app.rag.query_expansion → app.agents
    is a cycle that only resolves at runtime in the server. For this offline eval,
    we call litellm directly with settings-derived kwargs.
    """
    kw = {}
    if settings.model_api_base:
        kw["api_base"] = settings.model_api_base
    if settings.model_api_key:
        kw["api_key"] = settings.model_api_key
    response = await litellm.aembedding(
        model=settings.embedding_model,
        input=[text],
        **kw,
    )
    item = response.data[0]
    return item["embedding"] if isinstance(item, dict) else item.embedding

QUERIES_PATH = Path(__file__).parent / "queries.json"

# Threshold above which a "top-1" result is considered a MISS even if some
# article was returned. Used for negative-case scoring (off-topic queries
# should have no close result). Tune alongside settings.rag_distance_threshold.
NEGATIVE_DISTANCE_FLOOR = 0.55

# Sentinels in queries.json's `expect_title_any`:
#   __NONE__       → off-topic query; top-1 distance must be above the floor to pass.
#   __EMERGENCY__  → must be caught by the emergency router pre-RAG.
SENTINEL_NONE = "__NONE__"
SENTINEL_EMERGENCY = "__EMERGENCY__"


def _title_of(row) -> str:
    meta = row.metadata_json or {}
    return meta.get("title", "")


def _hit(row, expected: list[str]) -> bool:
    t = _title_of(row).lower()
    return any(e.lower() in t for e in expected)


def _classify_emergency_safe(query: str):
    """Import lazily — app.agents pulls in tools which pull in rag.retrieval."""
    try:
        from app.agents.emergency_router import classify_emergency
        return classify_emergency(query)
    except Exception:
        return None


async def run(top_n: int, label: str | None):
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    print(f"# RAG Eval{' [' + label + ']' if label else ''}")
    print(f"# queries: {len(queries)}   top_n: {top_n}\n")

    # Separate counters per query kind so negatives and emergencies don't
    # get folded into the retrieval top-N numbers.
    pos_total = pos_top1 = pos_topN = 0
    neg_total = neg_pass = 0
    emg_total = emg_pass = 0
    rows_out = []

    async with async_session() as db:
        for q in queries:
            query = q["query"]
            expected = q["expect_title_any"]

            kind = "positive"
            if SENTINEL_NONE in expected:
                kind = "negative"
            elif SENTINEL_EMERGENCY in expected:
                kind = "emergency"

            # Emergency queries should be caught pre-RAG. If they are, pass.
            # We still also do the retrieval lookup so we can see what RAG
            # would have returned (diagnostic, not part of the pass criteria).
            emergency_match = _classify_emergency_safe(query) if kind == "emergency" else None

            vec = await embed_text(query)
            distance = Embedding.embedding.cosine_distance(vec).label("distance")
            stmt = (
                select(Embedding, distance)
                .where(Embedding.source_type == SourceType.knowledge_base)
                .order_by(distance)
                .limit(top_n)
            )
            results = (await db.execute(stmt)).all()
            top_titles = [(_title_of(r), float(d)) for r, d in results]
            top1_dist = top_titles[0][1] if top_titles else None

            if kind == "positive":
                pos_total += 1
                top1_hit = _hit(results[0][0], expected) if results else False
                topN_hit = any(_hit(r, expected) for r, _ in results)
                pos_top1 += int(top1_hit)
                pos_topN += int(topN_hit)
                status = "✓" if topN_hit else "✗"
                top1_mark = "1" if top1_hit else "-"
                print(f"{status} [@1:{top1_mark}] {query!r}  → expected {expected}")
                for i, (t, d) in enumerate(top_titles):
                    mark = "★" if any(e.lower() in t.lower() for e in expected) else " "
                    print(f"     {i+1}. {mark} d={d:.3f}  {t}")
                rows_out.append({
                    "query": query, "kind": "positive",
                    "expected": expected,
                    "top1_hit": top1_hit, "topN_hit": topN_hit,
                    "top_titles": top_titles,
                })

            elif kind == "negative":
                neg_total += 1
                # Pass if top-1 distance is BEYOND the floor (i.e. no close match).
                passed = top1_dist is not None and top1_dist >= NEGATIVE_DISTANCE_FLOOR
                neg_pass += int(passed)
                status = "✓" if passed else "✗"
                print(f"{status} [NEG] {query!r}  top1_d={top1_dist:.3f}  (floor={NEGATIVE_DISTANCE_FLOOR})")
                print(f"      nearest: {top_titles[0][0] if top_titles else '—'}")
                rows_out.append({
                    "query": query, "kind": "negative",
                    "passed": passed, "top1_distance": top1_dist,
                    "top_titles": top_titles,
                })

            else:  # emergency
                emg_total += 1
                passed = emergency_match is not None
                emg_pass += int(passed)
                status = "✓" if passed else "✗"
                cat = emergency_match.category if emergency_match else "—"
                print(f"{status} [EMG] {query!r}  router_category={cat}")
                rows_out.append({
                    "query": query, "kind": "emergency",
                    "passed": passed,
                    "category": cat,
                    "fallback_top_titles": top_titles,
                })

            print()

    def _pct(n, d):
        return f"{n/d*100:.0f}%" if d else "n/a"

    print("=" * 60)
    print(f"POSITIVE  TOP-1:  {pos_top1}/{pos_total} = {_pct(pos_top1, pos_total)}")
    print(f"POSITIVE  TOP-{top_n}:  {pos_topN}/{pos_total} = {_pct(pos_topN, pos_total)}")
    print(f"NEGATIVE  reject: {neg_pass}/{neg_total} = {_pct(neg_pass, neg_total)}  (top1_d >= {NEGATIVE_DISTANCE_FLOOR})")
    print(f"EMERGENCY route:  {emg_pass}/{emg_total} = {_pct(emg_pass, emg_total)}")

    summary = {
        "positive_total": pos_total,
        "positive_top1": pos_top1,
        "positive_topN": pos_topN,
        "negative_total": neg_total,
        "negative_pass": neg_pass,
        "emergency_total": emg_total,
        "emergency_pass": emg_pass,
    }

    # also dump JSON next to queries.json for diffing
    if label:
        out = Path(__file__).parent / f"result_{label}.json"
        out.write_text(json.dumps({
            "label": label,
            "top_n": top_n,
            "summary": summary,
            "rows": rows_out,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {out}")

    return {"top_n": top_n, "summary": summary, "rows": rows_out}


def main():
    global QUERIES_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument(
        "--file",
        default=None,
        help="Override queries file. Defaults to knowledge/eval/queries.json. "
        "Use queries_en.json for the English eval.",
    )
    ap.add_argument("--label", help="Save JSON snapshot as result_<label>.json")
    args = ap.parse_args()
    if args.file:
        QUERIES_PATH = Path(args.file)
        if not QUERIES_PATH.is_absolute():
            QUERIES_PATH = Path(__file__).parent / args.file
    asyncio.run(run(args.top, args.label))


if __name__ == "__main__":
    main()
