from pathlib import Path
import json

from app.agent_harness.client import ChatResult
from app.agent_harness.graders import grade_result
from app.agent_harness.scenario import load_scenario
from tests.e2e.test_messages import MESSAGES


def test_builtin_agent_scenarios_load():
    scenario_dir = Path(__file__).parents[1] / "scenarios" / "agent"
    paths = sorted(scenario_dir.glob("*.json"))

    assert len(paths) >= 18
    ids = set()
    for path in paths:
        scenario = load_scenario(path)
        assert scenario.id
        assert scenario.id not in ids
        assert scenario.messages
        ids.add(scenario.id)


def test_builtin_agent_scenarios_include_new_zh_cases():
    scenario_dir = Path(__file__).parents[1] / "scenarios" / "agent"
    ids = {load_scenario(path).id for path in scenario_dir.glob("*.json")}

    assert {
        "zh_casual_chat_no_record",
        "zh_question_no_record",
        "zh_record_verb_bypass",
        "zh_statement_needs_confirm",
        "zh_delete_always_confirm",
        "zh_update_weight_bypass",
        "zh_mild_symptom_no_emergency",
        "zh_pushback_after_query",
    } <= ids


def test_builtin_agent_scenario_expectations_are_well_formed():
    scenario_dir = Path(__file__).parents[1] / "scenarios" / "agent"
    for path in sorted(scenario_dir.glob("*.json")):
        scenario = load_scenario(path)
        expect = scenario.expect
        # An executed tool is by definition also a called tool.
        assert not set(expect.tools_executed) & set(expect.forbidden_tools)
        assert not set(expect.cards) & set(expect.forbidden_cards)
        assert all(rubric.strip() for rubric in expect.judge)
        if expect.side_effects.absent_events:
            assert scenario.events, f"{scenario.id}: absent_events needs a seeded event"


def test_record_vomit_accepts_recording_opener():
    scenario_dir = Path(__file__).parents[1] / "scenarios" / "agent"
    scenario = load_scenario(scenario_dir / "02_record_vomit.json")
    result = ChatResult(
        text="Got it, recording that now...",
        cards=[{"type": "record"}],
        trace={"events": [{
            "type": "run_completed",
            "data": {
                "tools_called": ["create_calendar_event"],
                "tools_executed": ["create_calendar_event"],
            },
        }]},
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
