"""Eval report builders for scenario runs."""

from __future__ import annotations

from typing import Any


def build_eval_report(runs: list[Any]) -> dict[str, Any]:
    total = len(runs)
    passed = sum(1 for run in runs if run.grade.passed)
    failed = total - passed
    return {
        "schema_version": 1,
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / total if total else 0.0,
        "results": [
            {
                "scenario_id": run.grade.scenario_id,
                "passed": run.grade.passed,
                "reasons": run.grade.reasons,
                "tools_called": run.artifact.tools_called,
                "elapsed_ms": run.artifact.elapsed_ms,
                "total_tokens": run.artifact.total_tokens,
            }
            for run in runs
        ],
    }
