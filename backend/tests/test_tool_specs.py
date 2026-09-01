import json

from click.testing import CliRunner

from app.agent_harness.cli import cli
from app.agents.tools import get_tool_definitions
from app.agents.tools.registry import get_tool_specs, register_tool


def test_registered_tool_exposes_tool_spec():
    async def fake_handler(arguments, db, user_id):
        return {"ok": True}

    register_tool(
        "test_tool_spec",
        description="Test tool.",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        read_only=True,
        search_hint="Use for tool spec tests.",
    )(fake_handler)

    spec = get_tool_specs()["test_tool_spec"]

    assert spec.name == "test_tool_spec"
    assert spec.read_only is True
    assert spec.destructive is False
    assert spec.input_schema["required"] == ["value"]


def test_all_openai_tool_definitions_have_specs():
    definitions = get_tool_definitions()
    specs = get_tool_specs()

    missing = [
        item["function"]["name"]
        for item in definitions
        if item["function"]["name"] not in specs
    ]

    assert missing == []


def test_delete_tools_are_destructive_and_confirmed():
    specs = get_tool_specs()

    assert specs["delete_pet"].destructive is True
    assert specs["delete_pet"].requires_confirmation is True


def test_cli_tools_list_renders_manifest_flags():
    result = CliRunner().invoke(cli, ["tools", "list"])

    assert result.exit_code == 0
    assert "create_calendar_event" in result.output
    assert "read_only=false" in result.output
    assert "requires_confirmation=true" in result.output


def test_cli_tools_describe_outputs_manifest_json():
    result = CliRunner().invoke(cli, ["tools", "describe", "create_calendar_event"])

    assert result.exit_code == 0
    manifest = json.loads(result.output)
    assert manifest["name"] == "create_calendar_event"
    assert manifest["input_schema"]["type"] == "object"
    assert manifest["read_only"] is False
    assert manifest["requires_confirmation"] is True
