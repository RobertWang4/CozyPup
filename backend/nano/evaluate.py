"""Evaluate a predictor on a labelled YAML file. Metrics that matter:
recall on true (missed emergencies), precision (wasted expensive calls)."""
from __future__ import annotations

import json, time
from pathlib import Path

import yaml


def load_rows(path: str) -> list[dict]:
    rows = yaml.safe_load(open(path)) or []
    return [{"msg": str(r["msg"]), "label": bool(r["label"]), "tags": r.get("tags", [])} for r in rows]


def metrics(labels: list[bool], probs: list[float], thr: float) -> dict:
    tp = sum(1 for y, p in zip(labels, probs) if y and p >= thr)
    fp = sum(1 for y, p in zip(labels, probs) if not y and p >= thr)
    fn = sum(1 for y, p in zip(labels, probs) if y and p < thr)
    tn = len(labels) - tp - fp - fn
    rec = tp / (tp + fn) if tp + fn else 0.0
    prec = tp / (tp + fp) if tp + fp else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"thr": thr, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": rec, "precision": prec, "f1": f1, "accuracy": (tp + tn) / len(labels)}


def evaluate(name: str, predict, rows: list[dict], thr: float = 0.5, report_dir: str = "reports") -> dict:
    t0 = time.time()
    probs = predict([r["msg"] for r in rows])
    elapsed = time.time() - t0
    labels = [r["label"] for r in rows]
    main = metrics(labels, probs, thr)
    sweep = [metrics(labels, probs, t) for t in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)]
    errors = [
        {"msg": r["msg"], "label": r["label"], "p": round(p, 3), "tags": r["tags"],
         "kind": "MISS" if r["label"] else "FALSE_ALARM"}
        for r, p in zip(rows, probs) if (p >= thr) != r["label"]
    ]
    errors.sort(key=lambda e: (e["kind"] != "MISS", -abs(e["p"] - thr)))
    report = {"name": name, "n": len(rows), "n_true": sum(labels), "elapsed_s": round(elapsed, 1),
              "metrics": main, "sweep": sweep, "errors": errors}

    Path(report_dir).mkdir(exist_ok=True)
    out = Path(report_dir) / f"nano_{name}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    m = main
    print(f"\n== {name} ==  n={len(rows)} (true={sum(labels)})  {elapsed:.1f}s")
    print(f"thr={thr}  recall={m['recall']:.3f}  precision={m['precision']:.3f}  f1={m['f1']:.3f}  acc={m['accuracy']:.3f}")
    print(f"TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']}")
    if len(set(probs)) > 2:
        print("thr   recall  precision")
        for s in sweep:
            print(f"{s['thr']:.1f}   {s['recall']:.3f}   {s['precision']:.3f}")
    miss = [e for e in errors if e["kind"] == "MISS"]
    fa = [e for e in errors if e["kind"] != "MISS"]
    print(f"\nMISSED ({len(miss)}):")
    for e in miss[:25]: print(f"  p={e['p']:.2f} {e['tags'][:3]} | {e['msg']}")
    print(f"\nFALSE ALARMS ({len(fa)}), showing 15:")
    for e in fa[:15]: print(f"  p={e['p']:.2f} {e['tags'][:3]} | {e['msg']}")
    print(f"\nreport: {out}")
    return report
