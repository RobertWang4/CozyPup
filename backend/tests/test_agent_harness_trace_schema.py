from app.agent_harness.client import ChatResult
from app.agent_harness.trace_schema import TraceArtifact, normalize_trace_artifact


def test_normalize_trace_artifact_extracts_core_fields():
    result = ChatResult(
        text="Done.",
        cards=[{"type": "record", "title": "Vaccine"}],
        session_id="s1",
        elapsed_ms=1234,
        trace={
            "total_prompt_tokens": 100,
            "total_completion_tokens": 20,
            "steps": [
                {"step": "pre_process", "elapsed_ms": 5, "data": [{"tool": "create_calendar_event"}]},
                {
                    "step": "tool_dispatch",
                    "elapsed_ms": 800,
                    "data": {
                        "round": 0,
                        "tool": "create_calendar_event",
                        "args": "{\"title\":\"Vaccine\"}",
                        "success": True,
                    },
                },
            ],
        },
    )

    artifact = normalize_trace_artifact(
        scenario_id="calendar_vaccine",
        user_email="harness@example.com",
        input_messages=["Remind me about Weiwei's vaccine tomorrow"],
        result=result,
    )

    assert artifact.schema_version == 1
    assert artifact.scenario_id == "calendar_vaccine"
    assert artifact.output_text == "Done."
    assert artifact.tools_called == ["create_calendar_event"]
    assert artifact.total_tokens == 120
    assert artifact.cards[0]["type"] == "record"
    assert artifact.raw_trace["steps"][1]["step"] == "tool_dispatch"


def test_trace_artifact_round_trips_as_json():
    artifact = TraceArtifact(
        schema_version=1,
        scenario_id="basic_chat",
        user_email="harness@example.com",
        input_messages=["hello"],
        output_text="hi",
        tools_called=[],
        cards=[],
        elapsed_ms=10,
        total_prompt_tokens=1,
        total_completion_tokens=2,
        total_tokens=3,
        raw_trace={"steps": []},
    )

    loaded = TraceArtifact.from_dict(artifact.to_dict())

    assert loaded == artifact
