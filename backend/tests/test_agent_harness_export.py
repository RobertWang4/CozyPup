import json

from click.testing import CliRunner

from app.agent_harness.cli import cli
from app.agent_harness.export import trace_to_sft_row
from app.agent_harness.trace_schema import TraceArtifact


def _artifact() -> TraceArtifact:
    return TraceArtifact(
        schema_version=1,
        scenario_id="record_vomit",
        user_email="harness@example.com",
        input_messages=["Record that Max vomited twice today."],
        output_text="Recorded.",
        tools_called=["create_calendar_event"],
        cards=[{"type": "record"}],
        elapsed_ms=10,
        total_prompt_tokens=1,
        total_completion_tokens=2,
        total_tokens=3,
        raw_trace={
            "steps": [
                {
                    "step": "tool_dispatch",
                    "data": {
                        "tool": "create_calendar_event",
                        "args": "{\"title\":\"Vomiting\"}",
                        "success": True,
                    },
                }
            ]
        },
    )


def test_trace_to_sft_row_includes_tool_calls():
    row = trace_to_sft_row(_artifact(), success=True)

    assert row["metadata"]["success"] is True
    assert row["metadata"]["scenario"] == "record_vomit"
    assert row["metadata"]["tools_called"] == ["create_calendar_event"]
    assert row["messages"][0]["role"] == "user"
    assert row["messages"][1]["role"] == "assistant"
    assert row["messages"][1]["tool_calls"][0]["function"]["name"] == "create_calendar_event"
    assert row["messages"][-1] == {"role": "assistant", "content": "Recorded."}


def test_cli_run_can_export_jsonl(monkeypatch, tmp_path):
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(json.dumps({
        "id": "record_vomit",
        "description": "Record vomit",
        "messages": ["Record that Max vomited twice today."],
        "expect": {},
    }))
    export_path = tmp_path / "sft.jsonl"

    class FakeRunner:
        def __init__(self, client):
            pass

        async def run(self, scenario):
            from app.agent_harness.graders import ScenarioGrade
            from app.agent_harness.client import ChatResult

            return type("Run", (), {
                "grade": ScenarioGrade(scenario.id, True, []),
                "result": ChatResult(text="Recorded."),
                "artifact": _artifact(),
            })()

    class FakeClient:
        def __init__(self, base_url, debug=False):
            pass

        async def close(self):
            pass

    monkeypatch.setattr("app.agent_harness.cli.AgentHarnessClient", FakeClient)
    monkeypatch.setattr("app.agent_harness.cli.ScenarioRunner", FakeRunner)

    result = CliRunner().invoke(cli, [
        "run",
        str(scenario_path),
        "--base-url",
        "http://test",
        "--export-jsonl",
        str(export_path),
    ])

    assert result.exit_code == 0
    rows = [json.loads(line) for line in export_path.read_text().splitlines()]
    assert rows[0]["metadata"]["scenario"] == "record_vomit"
    assert rows[0]["metadata"]["success"] is True
