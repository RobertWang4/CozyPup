import base64
import json

import httpx
import pytest
from click.testing import CliRunner

from app.agent_harness.client import AgentHarnessClient, ChatResult, build_chat_result, get_tools_called, load_test_image
from app.agent_harness.cli import PROD_BASE_URL, cli
from app.agent_harness.graders import ScenarioGrade
from app.agent_harness.report import build_eval_report
from app.agent_harness.render import render_result
from app.agent_harness.trace_schema import TraceArtifact


def test_build_chat_result_parses_sse_events():
    raw = "\n".join([
        'event: token',
        'data: {"text": "Hello"}',
        '',
        'event: card',
        'data: {"type": "record", "title": "Vomiting"}',
        '',
        'event: __debug__',
        'data: {"steps": [{"step": "tool_dispatch", "data": {"tool": "create_calendar_event"}}]}',
        '',
        'event: done',
        'data: {"session_id": "s1"}',
        '',
    ])

    result = build_chat_result(raw, elapsed_ms=42)

    assert result.text == "Hello"
    assert result.session_id == "s1"
    assert result.first_card("record")["title"] == "Vomiting"
    assert get_tools_called(result) == ["create_calendar_event"]


def test_load_test_image_returns_jpeg_bytes():
    image_bytes = base64.b64decode(load_test_image())

    assert image_bytes.startswith(b"\xff\xd8")
    assert image_bytes.endswith(b"\xff\xd9")


@pytest.mark.asyncio
async def test_auth_dev_retries_transient_connect_error(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "token-1", "user_id": "user-1"}

    class FakeAsyncClient:
        def __init__(self):
            self.calls = 0

        async def post(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ConnectError("transient connect error")
            return FakeResponse()

    client = AgentHarnessClient("https://api.example.com")
    fake = FakeAsyncClient()
    client._client = fake

    await client.auth_dev(email="harness@example.com")

    assert fake.calls == 2
    assert client.token == "token-1"
    assert client.user_id == "user-1"
    assert client.email == "harness@example.com"


def test_render_result_includes_verbose_trace():
    result = ChatResult(
        text="Recorded.",
        cards=[{"type": "record", "category": "abnormal"}],
        elapsed_ms=1200,
        trace={
            "total_prompt_tokens": 100,
            "total_completion_tokens": 20,
            "steps": [
                {"step": "pre_process", "elapsed_ms": 5, "data": [{"tool": "create_calendar_event"}]},
                {"step": "tool_dispatch", "elapsed_ms": 900, "data": {"tool": "create_calendar_event"}},
            ],
        },
    )

    rendered = render_result(result, verbose=True)

    assert "RESPONSE" in rendered
    assert "Recorded." in rendered
    assert "CARDS" in rendered
    assert "create_calendar_event" in rendered
    assert "prompt=100" in rendered


def test_render_result_includes_stable_events_in_verbose_trace():
    result = ChatResult(
        text="Recorded.",
        elapsed_ms=1200,
        trace={
            "events": [
                {"type": "model_started", "elapsed_ms": 1, "data": {"round": 0}},
                {"type": "tool_call_started", "elapsed_ms": 10, "data": {"tool": "create_calendar_event"}},
            ],
        },
    )

    rendered = render_result(result, verbose=True)

    assert "EVENTS" in rendered
    assert "model_started" in rendered
    assert "tool_call_started" in rendered


def test_cli_chat_uses_harness_client(monkeypatch):
    calls = {}

    class FakeClient:
        def __init__(self, base_url, debug=False):
            calls["base_url"] = base_url
            calls["debug"] = debug

        async def auth_dev(self, email=None):
            calls["email"] = email

        async def create_pet(self, name, species="dog"):
            calls["pet"] = (name, species)
            return {"id": "p1", "name": name, "species": species}

        async def chat(self, message, **kwargs):
            calls["message"] = message
            return ChatResult(
                text="ok",
                trace={"steps": [{"step": "tool_dispatch", "data": {"tool": "list_pets"}}]},
            )

        async def close(self):
            calls["closed"] = True

    monkeypatch.setattr("app.agent_harness.cli.AgentHarnessClient", FakeClient)

    runner = CliRunner()
    result = runner.invoke(cli, [
        "chat",
        "hello",
        "--base-url",
        "http://test",
        "--email",
        "dev@example.com",
        "--debug",
        "--verbose",
        "--pet",
        "Weiwei:dog",
    ])

    assert result.exit_code == 0
    assert "ok" in result.output
    assert "list_pets" in result.output
    assert calls == {
        "base_url": "http://test",
        "debug": True,
        "email": "dev@example.com",
        "pet": ("Weiwei", "dog"),
        "message": "hello",
        "closed": True,
    }


def test_cli_chat_env_prod_uses_prod_base_url(monkeypatch):
    calls = {}

    class FakeClient:
        def __init__(self, base_url, debug=False):
            calls["base_url"] = base_url

        async def auth_dev(self, email=None):
            pass

        async def chat(self, message, **kwargs):
            return ChatResult(text="ok")

        async def close(self):
            pass

    monkeypatch.setattr("app.agent_harness.cli.AgentHarnessClient", FakeClient)

    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "hello", "--env", "prod"])

    assert result.exit_code == 0
    assert calls["base_url"] == PROD_BASE_URL


def test_cli_chat_connection_error_is_friendly(monkeypatch):
    class FakeClient:
        def __init__(self, base_url, debug=False):
            self.base_url = base_url

        async def auth_dev(self, email=None):
            raise httpx.ConnectError("All connection attempts failed")

        async def close(self):
            pass

    monkeypatch.setattr("app.agent_harness.cli.AgentHarnessClient", FakeClient)

    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "hello", "--base-url", "https://api.example.com"])

    assert result.exit_code != 0
    assert "Could not connect" in result.output
    assert "https://api.example.com" in result.output
    assert "--base-url" in result.output
    assert "Traceback" not in result.output


def test_cli_chat_can_save_trace_artifact(monkeypatch, tmp_path):
    out_path = tmp_path / "trace.json"

    class FakeClient:
        def __init__(self, base_url, debug=False):
            self.email = "harness@example.com"

        async def auth_dev(self, email=None):
            self.email = email or self.email

        async def chat(self, message, **kwargs):
            return ChatResult(
                text="ok",
                elapsed_ms=10,
                trace={"steps": [], "total_prompt_tokens": 1, "total_completion_tokens": 2},
            )

        async def close(self):
            pass

    monkeypatch.setattr("app.agent_harness.cli.AgentHarnessClient", FakeClient)

    runner = CliRunner()
    result = runner.invoke(cli, [
        "chat",
        "hello",
        "--base-url",
        "http://test",
        "--debug",
        "--save-trace",
        str(out_path),
    ])

    assert result.exit_code == 0
    saved = json.loads(out_path.read_text())
    assert saved["schema_version"] == 1
    assert saved["input_messages"] == ["hello"]
    assert saved["output_text"] == "ok"


def test_cli_replay_renders_saved_trace(tmp_path):
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(json.dumps({
        "schema_version": 1,
        "scenario_id": "basic",
        "user_email": "harness@example.com",
        "input_messages": ["hello"],
        "output_text": "hi",
        "tools_called": ["list_pets"],
        "cards": [],
        "elapsed_ms": 11,
        "total_prompt_tokens": 1,
        "total_completion_tokens": 2,
        "total_tokens": 3,
        "raw_trace": {"steps": []},
    }))

    runner = CliRunner()
    result = runner.invoke(cli, ["replay", str(trace_path)])

    assert result.exit_code == 0
    assert "hi" in result.output
    assert "list_pets" in result.output


def test_cli_run_scenario_prints_grade(monkeypatch, tmp_path):
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(json.dumps({
        "id": "basic",
        "description": "Basic",
        "messages": ["hello"],
        "expect": {"contains_any": ["ok"]},
    }))

    class FakeRunner:
        def __init__(self, client, judge=True):
            pass

        async def run(self, scenario):
            from app.agent_harness.graders import ScenarioGrade
            from app.agent_harness.trace_schema import TraceArtifact
            return type("Run", (), {
                "grade": ScenarioGrade(scenario.id, True, []),
                "result": ChatResult(text="ok"),
                "artifact": TraceArtifact(
                    schema_version=1,
                    scenario_id=scenario.id,
                    user_email="harness@example.com",
                    input_messages=scenario.messages,
                    output_text="ok",
                    tools_called=[],
                    cards=[],
                    elapsed_ms=1,
                    total_prompt_tokens=0,
                    total_completion_tokens=0,
                    total_tokens=0,
                    raw_trace={},
                ),
            })()

    class FakeClient:
        def __init__(self, base_url, debug=False):
            pass

        async def close(self):
            pass

    monkeypatch.setattr("app.agent_harness.cli.AgentHarnessClient", FakeClient)
    monkeypatch.setattr("app.agent_harness.cli.ScenarioRunner", FakeRunner, raising=False)

    runner = CliRunner()
    result = runner.invoke(cli, ["run", str(scenario_path), "--base-url", "http://test"])

    assert result.exit_code == 0
    assert "PASS basic" in result.output
    assert "ok" in result.output


def test_build_eval_report_counts_passes_and_failures():
    runs = [
        type("Run", (), {
            "grade": ScenarioGrade("a", True, []),
            "artifact": TraceArtifact(1, "a", "u", ["hi"], "ok", [], [], 1, 0, 0, 0, {}),
        })(),
        type("Run", (), {
            "grade": ScenarioGrade("b", False, ["missing tool: list_pets"]),
            "artifact": TraceArtifact(1, "b", "u", ["pets"], "ok", [], [], 2, 3, 4, 7, {}),
        })(),
    ]

    report = build_eval_report(runs)

    assert report["total"] == 2
    assert report["schema_version"] == 2
    assert report["passed"] == 1
    assert report["failed"] == 1
    assert report["pass_rate"] == 0.5
    assert report["pass_all_rate"] == 0.5
    assert report["results"][1]["reasons"] == ["missing tool: list_pets"]
    assert report["results"][1]["total_tokens"] == 7
    assert report["results"][1]["runs"][0]["passed"] is False


def test_cli_eval_scenario_dir_writes_report(monkeypatch, tmp_path):
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "a.json").write_text(json.dumps({
        "id": "a",
        "description": "A",
        "messages": ["hello"],
        "expect": {},
    }))
    (scenario_dir / "b.json").write_text(json.dumps({
        "id": "b",
        "description": "B",
        "messages": ["pets"],
        "expect": {},
    }))
    report_path = tmp_path / "report.json"

    class FakeRunner:
        def __init__(self, client, judge=True):
            pass

        async def run(self, scenario):
            passed = scenario.id == "a"
            return type("Run", (), {
                "grade": ScenarioGrade(
                    scenario.id,
                    passed,
                    [] if passed else ["missing tool: list_pets"],
                ),
                "artifact": TraceArtifact(
                    schema_version=1,
                    scenario_id=scenario.id,
                    user_email="harness@example.com",
                    input_messages=scenario.messages,
                    output_text="ok",
                    tools_called=["list_pets"] if scenario.id == "b" else [],
                    cards=[],
                    elapsed_ms=1,
                    total_prompt_tokens=0,
                    total_completion_tokens=0,
                    total_tokens=0,
                    raw_trace={},
                ),
            })()

    class FakeClient:
        def __init__(self, base_url, debug=False):
            pass

        async def close(self):
            pass

    monkeypatch.setattr("app.agent_harness.cli.AgentHarnessClient", FakeClient)
    monkeypatch.setattr("app.agent_harness.cli.ScenarioRunner", FakeRunner)

    runner = CliRunner()
    result = runner.invoke(cli, [
        "eval",
        str(scenario_dir),
        "--base-url",
        "http://test",
        "--report",
        str(report_path),
    ])

    assert result.exit_code == 0
    assert "PASS RATE 1/2 (50%)" in result.output
    assert "PASS a 1/1" in result.output
    assert "FAIL b 0/1" in result.output
    saved = json.loads(report_path.read_text())
    assert saved["total"] == 2
    assert saved["failed"] == 1


def test_cli_eval_can_write_per_scenario_traces(monkeypatch, tmp_path):
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    for scenario_id in ["a", "b"]:
        (scenario_dir / f"{scenario_id}.json").write_text(json.dumps({
            "id": scenario_id,
            "description": scenario_id,
            "messages": ["hello"],
            "expect": {},
        }))
    trace_dir = tmp_path / "traces"

    class FakeRunner:
        def __init__(self, client, judge=True):
            pass

        async def run(self, scenario):
            return type("Run", (), {
                "grade": ScenarioGrade(scenario.id, True, []),
                "artifact": TraceArtifact(
                    schema_version=1,
                    scenario_id=scenario.id,
                    user_email="harness@example.com",
                    input_messages=scenario.messages,
                    output_text="ok",
                    tools_called=[],
                    cards=[],
                    elapsed_ms=1,
                    total_prompt_tokens=0,
                    total_completion_tokens=0,
                    total_tokens=0,
                    raw_trace={"events": [{"type": "run_completed", "data": {}}]},
                ),
            })()

    class FakeClient:
        def __init__(self, base_url, debug=False):
            pass

        async def close(self):
            pass

    monkeypatch.setattr("app.agent_harness.cli.AgentHarnessClient", FakeClient)
    monkeypatch.setattr("app.agent_harness.cli.ScenarioRunner", FakeRunner)

    result = CliRunner().invoke(cli, [
        "eval",
        str(scenario_dir),
        "--base-url",
        "http://test",
        "--trace-dir",
        str(trace_dir),
    ])

    assert result.exit_code == 0
    assert (trace_dir / "a.trace.json").exists()
    assert (trace_dir / "b.trace.json").exists()
    saved = json.loads((trace_dir / "a.trace.json").read_text())
    assert saved["raw_trace"]["events"][0]["type"] == "run_completed"


def test_cli_eval_fail_fast_stops_after_first_failure(monkeypatch, tmp_path):
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    for scenario_id in ["a", "b"]:
        (scenario_dir / f"{scenario_id}.json").write_text(json.dumps({
            "id": scenario_id,
            "description": scenario_id,
            "messages": ["hello"],
            "expect": {},
        }))

    seen = []

    class FakeRunner:
        def __init__(self, client, judge=True):
            pass

        async def run(self, scenario):
            seen.append(scenario.id)
            passed = scenario.id != "a"
            return type("Run", (), {
                "grade": ScenarioGrade(
                    scenario.id,
                    passed,
                    [] if passed else ["missing tool: create_calendar_event"],
                ),
                "artifact": TraceArtifact(
                    schema_version=1,
                    scenario_id=scenario.id,
                    user_email="harness@example.com",
                    input_messages=scenario.messages,
                    output_text="ok",
                    tools_called=[],
                    cards=[],
                    elapsed_ms=1,
                    total_prompt_tokens=0,
                    total_completion_tokens=0,
                    total_tokens=0,
                    raw_trace={},
                ),
            })()

    class FakeClient:
        def __init__(self, base_url, debug=False):
            pass

        async def close(self):
            pass

    monkeypatch.setattr("app.agent_harness.cli.AgentHarnessClient", FakeClient)
    monkeypatch.setattr("app.agent_harness.cli.ScenarioRunner", FakeRunner)

    result = CliRunner().invoke(cli, [
        "eval",
        str(scenario_dir),
        "--base-url",
        "http://test",
        "--fail-fast",
    ])

    assert result.exit_code == 0
    assert seen == ["a"]
    assert "FAIL a 0/1" in result.output
