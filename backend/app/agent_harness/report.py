"""Eval report builders for scenario runs."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 2

TOKEN_REGRESSION_RATIO = 1.3


def _run_entry(run: Any) -> dict[str, Any]:
    artifact = run.artifact
    return {
        "passed": run.grade.passed,
        "reasons": run.grade.reasons,
        "elapsed_ms": artifact.elapsed_ms,
        "total_tokens": artifact.total_tokens,
        "llm_rounds": len(artifact.raw_trace.get("llm_rounds") or []),
        "tools_called": artifact.tools_called,
        "tools_executed": artifact.tools_executed,
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def build_eval_report(runs: list[Any]) -> dict[str, Any]:
    """Aggregate scenario runs, grouping repeats of the same scenario."""
    grouped: dict[str, list[Any]] = {}
    for run in runs:
        grouped.setdefault(run.grade.scenario_id, []).append(run)

    results = []
    for scenario_id, scenario_runs in grouped.items():
        entries = [_run_entry(run) for run in scenario_runs]
        passes = sum(1 for entry in entries if entry["passed"])
        reasons: list[str] = []
        for entry in entries:
            for reason in entry["reasons"]:
                if reason not in reasons:
                    reasons.append(reason)
        last = scenario_runs[-1].artifact
        results.append({
            "scenario_id": scenario_id,
            "passed": passes == len(entries),
            "pass_all": passes == len(entries),
            "passes": passes,
            "total_runs": len(entries),
            "pass_rate": passes / len(entries),
            "reasons": reasons,
            "tools_called": last.tools_called,
            "tools_executed": last.tools_executed,
            "elapsed_ms": int(_mean([entry["elapsed_ms"] for entry in entries])),
            "total_tokens": int(_mean([entry["total_tokens"] for entry in entries])),
            "llm_rounds": _mean([entry["llm_rounds"] for entry in entries]),
            "runs": entries,
        })

    total = len(results)
    passed = sum(1 for item in results if item["pass_all"])
    total_runs = sum(item["total_runs"] for item in results)
    total_passes = sum(item["passes"] for item in results)
    return {
        "schema_version": SCHEMA_VERSION,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "total_runs": total_runs,
        "pass_rate": total_passes / total_runs if total_runs else 0.0,
        "pass_all_rate": passed / total if total else 0.0,
        "results": results,
    }


def _baseline_entry(item: dict[str, Any], schema_version: int) -> dict[str, Any]:
    """Normalize a report result entry; schema 1 entries are single runs."""
    if schema_version >= 2:
        return item
    return {
        **item,
        "pass_rate": 1.0 if item.get("passed") else 0.0,
        "llm_rounds": None,
    }


def compare_reports(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Return human-readable regression warnings for current vs baseline."""
    schema_version = int(baseline.get("schema_version", 1))
    base_by_id = {
        item["scenario_id"]: _baseline_entry(item, schema_version)
        for item in baseline.get("results", [])
    }

    warnings: list[str] = []
    for item in current.get("results", []):
        base = base_by_id.get(item["scenario_id"])
        if base is None:
            continue
        name = item["scenario_id"]

        base_rate = float(base.get("pass_rate", 0.0))
        if item["pass_rate"] < base_rate:
            warnings.append(
                f"{name}: pass_rate dropped {base_rate:.0%} -> {item['pass_rate']:.0%}"
            )

        base_tokens = float(base.get("total_tokens") or 0)
        if base_tokens > 0 and item["total_tokens"] > base_tokens * TOKEN_REGRESSION_RATIO:
            warnings.append(
                f"{name}: total_tokens {int(base_tokens)} -> {item['total_tokens']} "
                f"(>{TOKEN_REGRESSION_RATIO}x)"
            )

        base_rounds = base.get("llm_rounds")
        if base_rounds is not None and item["llm_rounds"] > float(base_rounds):
            warnings.append(
                f"{name}: llm_rounds {float(base_rounds):.1f} -> {item['llm_rounds']:.1f}"
            )

    return warnings
