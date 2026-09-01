import json
from datetime import date, timedelta

import pytest

from app.agent_harness.client import ChatResult
from app.agent_harness.graders import grade_result
from app.agent_harness.runner import ScenarioRunner
from app.agent_harness.scenario import (
    EventSideEffect,
    EventFixture,
    ExpectedOutcome,
    HarnessScenario,
    PetFixture,
    PetSideEffect,
    SideEffectExpectations,
    load_scenario,
)


def test_load_scenario_from_json(tmp_path):
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps({
        "id": "calendar_vomit",
        "description": "Record a vomiting event.",
        "language": "en",
        "auto_confirm": True,
        "pets": [{"name": "Max", "species": "dog"}],
        "events": [
            {
                "pet_name": "Max",
                "event_date": "today",
                "title": "Vomiting",
                "category": "abnormal",
                "raw_text": "Max vomited today.",
            }
        ],
        "messages": ["Record that Max vomited twice today."],
            "expect": {
                "tools": ["create_calendar_event"],
                "forbidden_tools": ["trigger_emergency"],
                "cards": ["record"],
                "contains_any": ["recorded", "saved"],
                "side_effects": {
                    "events": [
                        {
                            "pet_name": "Max",
                            "category": "abnormal",
                            "title_contains_any": ["vomit", "吐"],
                        }
                    ],
                    "pets": [
                        {
                            "name": "Max",
                            "species": "dog",
                        }
                    ],
                },
            },
    }))

    scenario = load_scenario(path)

    assert scenario.id == "calendar_vomit"
    assert scenario.language == "en"
    assert scenario.auto_confirm is True
    assert scenario.pets[0].name == "Max"
    assert scenario.events[0].pet_name == "Max"
    assert scenario.events[0].event_date == "today"
    assert scenario.events[0].title == "Vomiting"
    assert scenario.events[0].category == "abnormal"
    assert scenario.expect.tools == ["create_calendar_event"]
    assert scenario.expect.forbidden_tools == ["trigger_emergency"]
    assert scenario.expect.side_effects.events[0].pet_name == "Max"
    assert scenario.expect.side_effects.events[0].category == "abnormal"
    assert scenario.expect.side_effects.pets[0].name == "Max"


def test_grade_result_passes_matching_tool_card_and_text():
    scenario = HarnessScenario(
        id="calendar",
        description="",
        messages=["msg"],
        expect=ExpectedOutcome(
            tools=["create_calendar_event"],
            forbidden_tools=["trigger_emergency"],
            cards=["record"],
            contains_any=["recorded"],
        ),
    )
    result = ChatResult(
        text="The event was recorded.",
        cards=[{"type": "record"}],
        trace={"steps": [{"step": "tool_dispatch", "data": {"tool": "create_calendar_event"}}]},
    )

    grade = grade_result(scenario, result)

    assert grade.passed is True
    assert grade.reasons == []


def test_grade_result_reports_missing_and_forbidden_tools():
    scenario = HarnessScenario(
        id="bad",
        description="",
        messages=["msg"],
        expect=ExpectedOutcome(
            tools=["create_calendar_event"],
            forbidden_tools=["trigger_emergency"],
        ),
    )
    result = ChatResult(
        text="ok",
        trace={"steps": [{"step": "tool_dispatch", "data": {"tool": "trigger_emergency"}}]},
    )

    grade = grade_result(scenario, result)

    assert grade.passed is False
    assert "missing tool: create_calendar_event" in grade.reasons
    assert "forbidden tool called: trigger_emergency" in grade.reasons


def test_grade_result_checks_emergency_message_for_text_expectations():
    scenario = HarnessScenario(
        id="emergency",
        description="",
        messages=["msg"],
        expect=ExpectedOutcome(
            cards=["emergency"],
            emergency=True,
            contains_any=["emergency", "vet"],
        ),
    )
    result = ChatResult(
        text="",
        emergency={"message": "This is an emergency. Go to a vet now."},
        cards=[{"type": "emergency", "message": "This is an emergency. Go to a vet now."}],
    )

    grade = grade_result(scenario, result)

    assert grade.passed is True


@pytest.mark.asyncio
async def test_scenario_runner_creates_pets_and_runs_messages():
    calls = []

    class FakeClient:
        email = "harness@example.com"

        async def auth_dev(self, email=None):
            calls.append(("auth", email))

        async def create_pet(self, name, species):
            calls.append(("pet", name, species))

        async def chat(self, message, language=None):
            calls.append(("chat", message, language))
            return ChatResult(
                text="The event was recorded.",
                cards=[{"type": "record"}],
                trace={"steps": [{"step": "tool_dispatch", "data": {"tool": "create_calendar_event"}}]},
            )

        async def get_events(self):
            calls.append(("events",))
            return [{"pet_name": "Max", "category": "abnormal", "title": "Vomiting"}]

        async def get_pets(self):
            calls.append(("pets_get",))
            return [{"name": "Max", "species": "dog"}]

    scenario = HarnessScenario(
        id="calendar",
        description="",
        language="en",
        pets=[PetFixture("Max", "dog")],
        messages=["Record that Max vomited twice today."],
        expect=ExpectedOutcome(
            tools=["create_calendar_event"],
            cards=["record"],
            side_effects=SideEffectExpectations(
                events=[EventSideEffect(pet_name="Max", category="abnormal")],
                pets=[PetSideEffect(name="Max", species="dog")],
            ),
        ),
    )

    run = await ScenarioRunner(FakeClient()).run(scenario)

    assert run.grade.passed is True
    assert calls == [
        ("auth", None),
        ("pet", "Max", "dog"),
        ("chat", "Record that Max vomited twice today.", "en"),
        ("events",),
        ("pets_get",),
    ]
    assert run.artifact.scenario_id == "calendar"
    assert run.artifact.input_messages == ["Record that Max vomited twice today."]


@pytest.mark.asyncio
async def test_scenario_runner_seeds_events_before_chat():
    calls = []

    class FakeClient:
        email = "harness@example.com"

        async def auth_dev(self, email=None):
            calls.append(("auth", email))

        async def create_pet(self, name, species):
            calls.append(("pet", name, species))
            return {"id": "pet-1", "name": name, "species": species}

        async def create_event(self, **kwargs):
            calls.append(("event", kwargs))
            return {"id": "event-1", **kwargs}

        async def chat(self, message, language=None):
            calls.append(("chat", message, language))
            return ChatResult(
                text="Please confirm.",
                cards=[{"type": "confirm_action", "action_id": "action-1"}],
                trace={"events": [{"type": "run_completed", "data": {"tools_called": ["delete_calendar_event"]}}]},
            )

        async def get_events(self):
            return []

    scenario = HarnessScenario(
        id="delete_event",
        description="",
        language="en",
        pets=[PetFixture("Max", "dog")],
        events=[
            EventFixture(
                pet_name="Max",
                event_date="today",
                title="Vomiting",
                category="abnormal",
                raw_text="Max vomited today.",
            )
        ],
        messages=["Delete Max's vomiting record from today."],
        expect=ExpectedOutcome(
            tools=["delete_calendar_event"],
            cards=["confirm_action"],
        ),
    )

    run = await ScenarioRunner(FakeClient()).run(scenario)

    assert run.grade.passed is True
    assert calls == [
        ("auth", None),
        ("pet", "Max", "dog"),
        ("event", {
            "pet_id": "pet-1",
            "event_date": date.today().isoformat(),
            "title": "Vomiting",
            "category": "abnormal",
            "raw_text": "Max vomited today.",
        }),
        ("chat", "Delete Max's vomiting record from today.", "en"),
    ]


@pytest.mark.asyncio
async def test_scenario_runner_resolves_yesterday_event_fixture_date():
    calls = []

    class FakeClient:
        email = "harness@example.com"

        async def auth_dev(self, email=None):
            pass

        async def create_pet(self, name, species):
            return {"id": "pet-1", "name": name, "species": species}

        async def create_event(self, **kwargs):
            calls.append(kwargs)
            return {"id": "event-1", **kwargs}

        async def chat(self, message, language=None):
            return ChatResult(text="ok")

    scenario = HarnessScenario(
        id="delete_yesterday_event",
        description="",
        pets=[PetFixture("Max", "dog")],
        events=[
            EventFixture(
                pet_name="Max",
                event_date="yesterday",
                title="Walk",
                category="daily",
                raw_text="seed event",
            )
        ],
        messages=["Delete yesterday's record."],
    )

    await ScenarioRunner(FakeClient()).run(scenario)

    assert calls[0]["event_date"] == (date.today() - timedelta(days=1)).isoformat()


@pytest.mark.asyncio
async def test_scenario_runner_auto_confirms_pending_action_before_side_effect_checks():
    calls = []

    class FakeClient:
        email = "harness@example.com"

        async def auth_dev(self, email=None):
            calls.append(("auth", email))

        async def chat(self, message, language=None):
            calls.append(("chat", message, language))
            return ChatResult(
                text="Please confirm.",
                cards=[{"type": "confirm_action", "action_id": "action-1"}],
                trace={"events": [{"type": "run_completed", "data": {"tools_called": ["create_pet"]}}]},
            )

        async def confirm_action(self, action_id):
            calls.append(("confirm", action_id))
            return {"success": True, "card": {"type": "pet_created"}}

        async def get_pets(self):
            calls.append(("pets_get",))
            return [{"name": "Max", "species": "dog"}]

    scenario = HarnessScenario(
        id="create_pet",
        description="",
        language="en",
        auto_confirm=True,
        messages=["I have a new dog named Max."],
        expect=ExpectedOutcome(
            tools=["create_pet"],
            cards=["confirm_action"],
            side_effects=SideEffectExpectations(
                pets=[PetSideEffect(name="Max", species="dog")],
            ),
        ),
    )

    run = await ScenarioRunner(FakeClient()).run(scenario)

    assert run.grade.passed is True
    assert calls == [
        ("auth", None),
        ("chat", "I have a new dog named Max.", "en"),
        ("confirm", "action-1"),
        ("pets_get",),
    ]


@pytest.mark.asyncio
async def test_scenario_runner_fails_when_expected_side_effect_is_missing():
    class FakeClient:
        email = "harness@example.com"

        async def auth_dev(self, email=None):
            pass

        async def chat(self, message, language=None):
            return ChatResult(
                text="The event was recorded.",
                cards=[{"type": "record"}],
                trace={"steps": [{"step": "tool_dispatch", "data": {"tool": "create_calendar_event"}}]},
            )

        async def get_events(self):
            return []

    scenario = HarnessScenario(
        id="calendar",
        description="",
        messages=["Record that Max vomited twice today."],
        expect=ExpectedOutcome(
            tools=["create_calendar_event"],
            side_effects=SideEffectExpectations(
                events=[EventSideEffect(pet_name="Max", category="abnormal")],
            ),
        ),
    )

    run = await ScenarioRunner(FakeClient()).run(scenario)

    assert run.grade.passed is False
    assert "missing event side effect" in run.grade.reasons[0]


@pytest.mark.asyncio
async def test_scenario_runner_grades_tools_across_multi_turn_scenario():
    class FakeClient:
        email = "harness@example.com"

        async def auth_dev(self, email=None):
            pass

        async def chat(self, message, language=None):
            if message == "I have a dog named Max":
                return ChatResult(
                    text="Please confirm Max.",
                    cards=[{"type": "confirm_action", "action_id": "a1"}],
                    trace={"events": [{"type": "run_completed", "data": {"tools_called": ["create_pet"]}}]},
                )
            return ChatResult(
                text="Recorded.",
                cards=[{"type": "record"}],
                trace={"events": [{"type": "run_completed", "data": {"tools_called": ["create_calendar_event"]}}]},
            )

    scenario = HarnessScenario(
        id="multi_turn",
        description="",
        messages=["I have a dog named Max", "Max ate breakfast today"],
        expect=ExpectedOutcome(
            tools=["create_pet", "create_calendar_event"],
            cards=["confirm_action", "record"],
        ),
    )

    run = await ScenarioRunner(FakeClient()).run(scenario)

    assert run.grade.passed is True
