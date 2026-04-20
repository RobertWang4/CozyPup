"""Unified eval orchestrator: retrieval + safety + A/B, with trend tracking.

Runs the three eval modules back-to-back, aggregates their summaries into a
single snapshot under `eval_history/<ISO>.json`, and prints a delta table
vs the previous snapshot so a pass/regression is visible at a glance.

Usage:
    cd backend
    python -m knowledge.eval.run_all                 # full (≈10-15 min)
    python -m knowledge.eval.run_all --quick         # retrieval only (~2 min)
    python -m knowledge.eval.run_all --no-ab         # skip A/B (costs LLM $)
    python -m knowledge.eval.run_all --ab-max 10     # cap A/B sample size

Each sub-module is invoked as its own subprocess so event loops / module
globals don't cross-contaminate. Their existing --label flag writes a JSON
next to run_eval.py; this orchestrator reads those files and collates.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
HISTORY_DIR = HERE.parent.parent / "eval_history"
LATEST_LABEL = "_latest"


def _run(cmd: list[str]) -> int:
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(HERE.parent.parent))


def _read_json(p: Path) -> dict | None:
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _retrieval_summary(result_json: dict | None) -> dict | None:
    if not result_json:
        return None
    s = result_json.get("summary", {})
    tot = s.get("positive_total", 0) or 1
    return {
        "positive_total": s.get("positive_total", 0),
        "top1": s.get("positive_top1", 0),
        "top3": s.get("positive_topN", 0),
        "top1_pct": round(s.get("positive_top1", 0) / tot * 100, 1),
        "top3_pct": round(s.get("positive_topN", 0) / tot * 100, 1),
        "neg_pass": s.get("negative_pass", 0),
        "neg_total": s.get("negative_total", 0),
        "emg_pass": s.get("emergency_pass", 0),
        "emg_total": s.get("emergency_total", 0),
    }


def _safety_summary(e2e_json: dict | None) -> dict | None:
    if not e2e_json:
        return None
    tally = e2e_json.get("tally", {})
    per_kind = {}
    red_line_pass = True
    for kind, b in tally.items():
        per_kind[kind] = {"pass": b["pass"], "total": b["total"]}
        if kind.startswith("red_line") and b["pass"] != b["total"]:
            red_line_pass = False
    return {"per_kind": per_kind, "red_line_pass": red_line_pass}


def _ab_summary(ab_json: dict | None) -> dict | None:
    if not ab_json:
        return None
    rows = ab_json.get("results", [])
    dims = ["factual_grounding", "specificity", "safety_quality", "hallucination_risk"]
    out = {"n": len(rows), "dimensions": {}}
    for d in dims:
        valid = [r for r in rows if r.get("judge", {}).get("rag") and r.get("judge", {}).get("norag")]
        if not valid:
            continue
        rag_avg = sum(int(r["judge"]["rag"].get(d, 0) or 0) for r in valid) / len(valid)
        norag_avg = sum(int(r["judge"]["norag"].get(d, 0) or 0) for r in valid) / len(valid)
        rw = sum(1 for r in valid if r["judge"]["rag"].get(d, 0) > r["judge"]["norag"].get(d, 0))
        nw = sum(1 for r in valid if r["judge"]["rag"].get(d, 0) < r["judge"]["norag"].get(d, 0))
        tie = len(valid) - rw - nw
        out["dimensions"][d] = {
            "rag_avg": round(rag_avg, 2),
            "norag_avg": round(norag_avg, 2),
            "delta": round(rag_avg - norag_avg, 2),
            "win_loss_tie": [rw, nw, tie],
        }
    return out


def _latest_previous(current_path: Path) -> dict | None:
    if not HISTORY_DIR.exists():
        return None
    prior = sorted(p for p in HISTORY_DIR.glob("*.json") if p != current_path)
    if not prior:
        return None
    return json.loads(prior[-1].read_text(encoding="utf-8"))


def _fmt_delta(curr: float | None, prev: float | None) -> str:
    if curr is None or prev is None:
        return "   —  "
    d = curr - prev
    if abs(d) < 0.05:
        return "  ±0.0"
    return f"{d:+5.1f}"


def _print_report(snapshot: dict, previous: dict | None) -> None:
    print("\n" + "=" * 72)
    print(f"EVAL SNAPSHOT — {snapshot['timestamp']}")
    print("=" * 72)

    # retrieval
    r = snapshot.get("retrieval") or {}
    pr = (previous or {}).get("retrieval") or {}
    print("\nRetrieval (positive top1 / top3):")
    print(f"  {'lang':<6} {'top1%':>8} {'Δ':>7}  {'top3%':>8} {'Δ':>7}  neg/emg")
    for lang in ("zh", "en"):
        c = r.get(lang)
        p = pr.get(lang) if pr else None
        if not c:
            continue
        d1 = _fmt_delta(c["top1_pct"], p["top1_pct"] if p else None)
        d3 = _fmt_delta(c["top3_pct"], p["top3_pct"] if p else None)
        print(
            f"  {lang:<6} {c['top1_pct']:>7.1f}% {d1:>7}  "
            f"{c['top3_pct']:>7.1f}% {d3:>7}  "
            f"{c['neg_pass']}/{c['neg_total']}  {c['emg_pass']}/{c['emg_total']}"
        )

    # safety
    s = snapshot.get("safety")
    if s:
        ps = (previous or {}).get("safety") or {}
        pk = s["per_kind"]
        pk_prev = ps.get("per_kind", {})
        print(f"\nE2E Safety (red-line gate: {'PASS' if s['red_line_pass'] else 'FAIL'}):")
        for kind in sorted(pk):
            c = pk[kind]
            p = pk_prev.get(kind)
            marker = "★" if kind.startswith("red_line") else " "
            curr_pct = c["pass"] / c["total"] * 100 if c["total"] else 0
            prev_pct = (p["pass"] / p["total"] * 100) if p and p["total"] else None
            d = _fmt_delta(curr_pct, prev_pct)
            print(f"  {marker} {kind:<22} {c['pass']}/{c['total']} = {curr_pct:>5.1f}% {d:>7}")

    # ab
    a = snapshot.get("ab")
    if a:
        pa = (previous or {}).get("ab") or {}
        pd_prev = pa.get("dimensions", {})
        print(f"\nA/B RAG vs no-RAG (grounded judge, n={a['n']}):")
        print(f"  {'dimension':<22} {'Δ':>7} {'prev Δ':>9} {'rag:no:tie':>14}")
        for d, v in a["dimensions"].items():
            p = pd_prev.get(d)
            prev_str = f"{p['delta']:+.2f}" if p else "   —"
            wlt = v["win_loss_tie"]
            print(f"  {d:<22} {v['delta']:+7.2f} {prev_str:>9} {str(wlt):>14}")

    print("\n" + "=" * 72)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="Retrieval only (skip e2e + ab)")
    ap.add_argument("--no-ab", action="store_true", help="Skip A/B eval (saves LLM $)")
    ap.add_argument("--no-e2e", action="store_true", help="Skip E2E safety eval")
    ap.add_argument("--ab-max", type=int, default=15, help="Cap A/B sample size")
    ap.add_argument("--no-save", action="store_true", help="Do not write to eval_history/")
    args = ap.parse_args()

    py = sys.executable

    # --- 1. retrieval (zh + en) --------------------------------------------
    print("### Retrieval eval")
    _run([py, "-m", "knowledge.eval.run_eval", "--label", LATEST_LABEL])
    _run([py, "-m", "knowledge.eval.run_eval", "--file", "queries_en.json",
          "--label", f"{LATEST_LABEL}_en"])

    zh = _retrieval_summary(_read_json(HERE / f"result_{LATEST_LABEL}.json"))
    en = _retrieval_summary(_read_json(HERE / f"result_{LATEST_LABEL}_en.json"))

    snapshot: dict = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "retrieval": {"zh": zh, "en": en},
    }

    if not args.quick:
        # --- 2. e2e safety --------------------------------------------------
        if not args.no_e2e:
            print("\n### E2E safety eval")
            _run([py, "-m", "knowledge.eval.e2e_eval", "--label", LATEST_LABEL])
            snapshot["safety"] = _safety_summary(
                _read_json(HERE / f"e2e_result_{LATEST_LABEL}.json")
            )

        # --- 3. A/B --------------------------------------------------------
        if not args.no_ab:
            print(f"\n### A/B eval (max {args.ab_max})")
            _run([py, "-m", "knowledge.eval.ab_eval",
                  "--label", LATEST_LABEL, "--max", str(args.ab_max)])
            snapshot["ab"] = _ab_summary(
                _read_json(HERE / f"ab_result_{LATEST_LABEL}.json")
            )

    # --- 4. write history + report -----------------------------------------
    current_path = HISTORY_DIR / f"{snapshot['timestamp'].replace(':', '-')}.json"
    prev = _latest_previous(current_path) if HISTORY_DIR.exists() else None

    if not args.no_save:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        current_path.write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    _print_report(snapshot, prev)

    if not args.no_save:
        print(f"Saved snapshot: {current_path.relative_to(HERE.parent.parent)}")
    if prev:
        print("(Δ columns compare against previous snapshot.)")


if __name__ == "__main__":
    main()
