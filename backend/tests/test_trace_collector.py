from app.agents.runtime import AgentEvent
from app.agents.trace_collector import TraceCollector


def test_trace_collector_records_agent_event_in_export():
    trace = TraceCollector(active=True)

    trace.record_event(AgentEvent(type="tool_call_started", data={"tool": "create_calendar_event"}))

    exported = trace.to_dict()
    assert exported["events"][0]["type"] == "tool_call_started"
    assert exported["events"][0]["data"] == {"tool": "create_calendar_event"}
    assert isinstance(exported["events"][0]["elapsed_ms"], int)


def test_trace_collector_records_event_from_type_and_data():
    trace = TraceCollector(active=True)

    trace.record_event("model_started", {"model": "deepseek/deepseek-v4-flash"})

    assert trace.to_dict()["events"][0]["type"] == "model_started"
    assert trace.to_dict()["events"][0]["data"]["model"] == "deepseek/deepseek-v4-flash"


def test_inactive_trace_collector_does_not_record_events():
    trace = TraceCollector(active=False)

    trace.record_event("model_started", {"model": "deepseek/deepseek-v4-flash"})

    assert trace.to_dict()["events"] == []
