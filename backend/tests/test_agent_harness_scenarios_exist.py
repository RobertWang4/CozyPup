from pathlib import Path
import json

from app.agent_harness.client import ChatResult
from app.agent_harness.graders import grade_result
from app.agent_harness.scenario import load_scenario
from tests.e2e.test_messages import MESSAGES


def test_builtin_agent_scenarios_load():
    scenario_dir = Path(__file__).parents[1] / "scenarios" / "agent"
    paths = sorted(scenario_dir.glob("*.json"))

    assert len(paths) >= 10
    ids = set()
    for path in paths:
        scenario = load_scenario(path)
        assert scenario.id
        assert scenario.id not in ids
        assert scenario.messages
        ids.add(scenario.id)


def test_record_vomit_accepts_recording_opener():
    scenario_dir = Path(__file__).parents[1] / "scenarios" / "agent"
    scenario = load_scenario(scenario_dir / "02_record_vomit.json")
    result = ChatResult(
        text="Got it, recording that now...",
        cards=[{"type": "record"}],
        trace={"steps": [{"step": "tool_dispatch", "data": {"tool": "create_calendar_event"}}]},
    )

    grade = grade_result(scenario, result)

    assert grade.passed is True


def test_legacy_e2e_messages_are_migrated_to_harness_scenarios():
    scenario_dir = Path(__file__).parents[1] / "scenarios" / "agent" / "e2e"
    paths = sorted(scenario_dir.glob("*.json"))

    migrated = set()
    ids = set()
    for path in paths:
        data = json.loads(path.read_text())
        scenario = load_scenario(path)
        assert scenario.id
        assert scenario.id not in ids
        assert scenario.messages
        ids.add(scenario.id)

        source = data.get("source", {})
        if source.get("suite") == "legacy_e2e":
            migrated.add((source.get("case_id"), source.get("language")))

    expected = {
        (case_id, lang)
        for case_id, messages in MESSAGES.items()
        for lang in ("zh", "en")
        if lang in messages
    }

    assert expected <= migrated
