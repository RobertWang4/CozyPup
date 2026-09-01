import pytest

from app.agents.tool_invocation import ToolInvocation, parse_tool_invocation


def test_parse_tool_invocation_returns_name_args_and_id():
    raw = {
        "id": "call-1",
        "function": {
            "name": "create_pet",
            "arguments": "{\"name\":\"Max\",\"species\":\"dog\"}",
        },
    }

    assert parse_tool_invocation(raw) == ToolInvocation(
        id="call-1",
        name="create_pet",
        arguments={"name": "Max", "species": "dog"},
    )


def test_parse_tool_invocation_reports_invalid_json():
    raw = {"id": "call-1", "function": {"name": "create_pet", "arguments": "{"}}

    with pytest.raises(ValueError, match="Invalid JSON arguments"):
        parse_tool_invocation(raw)
