import json

from click.testing import CliRunner

from app.agent_harness.cli import cli
from app.agent_harness.graders import ScenarioGrade
from app.agent_harness.report import build_eval_report, compare_reports
from app.agent_harness.trace_schema import TraceArtifact


def _run(scenario_id, passed, *, tokens=100, rounds=1, reasons=None):
    return type("Run", (), {
        "grade": ScenarioGrade(scenario_id, passed, reasons or ([] if passed else ["missing tool: x"])),
        "artifact": TraceArtifact(
            schema_version=1,
            scenario_id=scenario_id,
            user_email="u",
            input_messages=["hi"],
            output_text="ok",
            tools_called=["create_calendar_event"],
            cards=[],
            elapsed_ms=10,
            total_prompt_tokens=0,
            total_completion_tokens=0,
            total_tokens=tokens,
            raw_trace={"llm_rounds": [{"round": i} for i in range(rounds)]},
            tools_executed=["create_calendar_event"] if passed else [],
        ),
    })()


def test_build_eval_report_aggregates_repeats_per_scenario():
    runs = [
        _run("a", True), _run("a", False), _run("a", True),
        _run("b", True), _run("b", True), _run("b", True),
    ]

    report = build_eval_report(runs)

    assert report["schema_version"] == 2
    assert report["total"] == 2
    assert report["total_runs"] == 6
    assert report["passed"] == 1
    assert report["pass_rate"] == 5 / 6
    assert report["pass_all_rate"] == 0.5

    scenario_a = report["results"][0]
    assert scenario_a["scenario_id"] == "a"
    assert scenario_a["passes"] == 2
    assert scenario_a["total_runs"] == 3
    assert scenario_a["pass_rate"] == 2 / 3
    assert scenario_a["pass_all"] is False
    assert scenario_a["reasons"] == ["missing tool: x"]
    assert len(scenario_a["runs"]) == 3
    assert scenario_a["runs"][1]["passed"] is False
    assert scenario_a["runs"][0]["llm_rounds"] == 1
    assert scenario_a["runs"][0]["tools_executed"] == ["create_calendar_event"]

    assert report["results"][1]["pass_all"] is True


def test_compare_reports_flags_pass_rate_token_and_round_regressions():
    baseline = build_eval_report([_run("a", True, tokens=1000, rounds=1)])
    current = build_eval_report([_run("a", False, tokens=1400, rounds=2)])

    warnings = compare_reports(baseline, current)

    assert any("pass_rate dropped" in w for w in warnings)
    assert any("total_tokens" in w for w in warnings)
    assert any("llm_rounds" in w for w in warnings)


def test_compare_reports_is_quiet_when_nothing_regressed():
    baseline = build_eval_report([_run("a", True, tokens=1000, rounds=2)])
    current = build_eval_report([_run("a", True, tokens=1100, rounds=2)])

    assert compare_reports(baseline, current) == []


def test_compare_reports_treats_schema_v1_baseline_as_single_run():
    baseline = {
        "schema_version": 1,
        "results": [{"scenario_id": "a", "passed": True, "total_tokens": 1000}],
    }
    current = build_eval_report([_run("a", False, tokens=1000, rounds=3)])

    warnings = compare_reports(baseline, current)

    assert warnings == ["a: pass_rate dropped 100% -> 0%"]


def _fake_harness(monkeypatch, seen):
    class FakeRunner:
        def __init__(self, client, judge=True):
            self.judge = judge

        async def run(self, scenario):
            seen.append((scenario.id, self.judge))
            passed = len([s for s, _ in seen if s == scenario.id]) != 2
            return _run(scenario.id, passed)

    class FakeClient:
        def __init__(self, base_url, debug=False):
            seen.append(("client", base_url))

        async def close(self):
            pass

    monkeypatch.setattr("app.agent_harness.cli.AgentHarnessClient", FakeClient)
    monkeypatch.setattr("app.agent_harness.cli.ScenarioRunner", FakeRunner)


def test_cli_eval_repeat_uses_fresh_client_per_run_and_reports_rates(monkeypatch, tmp_path):
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "a.json").write_text(json.dumps({
        "id": "a", "description": "A", "messages": ["hello"], "expect": {},
    }))
    report_path = tmp_path / "report.json"
    seen = []
    _fake_harness(monkeypatch, seen)

    result = CliRunner().invoke(cli, [
        "eval", str(scenario_dir), "--base-url", "http://test",
        "--repeat", "3", "--no-judge", "--report", str(report_path),
    ])

    assert result.exit_code == 0
    assert [item for item in seen if item[0] == "client"] == [("client", "http://test")] * 3
    assert all(judge is False for name, judge in seen if name == "a")
    assert "PASS RATE 0/1" in result.output
    assert "RUN PASS RATE 67%" in result.output

    saved = json.loads(report_path.read_text())
    assert saved["results"][0]["passes"] == 2
    assert saved["results"][0]["total_runs"] == 3


def test_cli_eval_baseline_prints_and_records_regressions(monkeypatch, tmp_path):
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "a.json").write_text(json.dumps({
        "id": "a", "description": "A", "messages": ["hello"], "expect": {},
    }))
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(build_eval_report([_run("a", True, tokens=1000)])))
    report_path = tmp_path / "report.json"

    class FakeRunner:
        def __init__(self, client, judge=True):
            pass

        async def run(self, scenario):
            return _run(scenario.id, False, tokens=1000)

    class FakeClient:
        def __init__(self, base_url, debug=False):
            pass

        async def close(self):
            pass

    monkeypatch.setattr("app.agent_harness.cli.AgentHarnessClient", FakeClient)
    monkeypatch.setattr("app.agent_harness.cli.ScenarioRunner", FakeRunner)

    result = CliRunner().invoke(cli, [
        "eval", str(scenario_dir), "--base-url", "http://test",
        "--baseline", str(baseline_path), "--report", str(report_path),
    ])

    assert result.exit_code == 0
    assert "REGRESSION a: pass_rate dropped 100% -> 0%" in result.output
    assert json.loads(report_path.read_text())["regressions"]
