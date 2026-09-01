from app.agents.runtime import AgentEvent, AgentRunResult, RunStatus


def test_agent_event_serializes_to_sse_payload():
    event = AgentEvent(type="tool_call_started", data={"tool": "create_calendar_event"})

    assert event.to_sse() == {
        "event": "tool_call_started",
        "data": {"tool": "create_calendar_event"},
    }


def test_run_result_has_success_status_and_metrics():
    result = AgentRunResult.success(
        response_text="Recorded.",
        rounds=1,
        tools_called=["create_calendar_event"],
        elapsed_ms=120,
    )

    assert result.status == RunStatus.SUCCESS
    assert result.ok is True
    assert result.tools_called == ["create_calendar_event"]
