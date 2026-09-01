"""Scenario runner for the CozyPup agent harness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .client import AgentHarnessClient, ChatResult
from .graders import ScenarioGrade, grade_result, grade_side_effects
from .scenario import HarnessScenario
from .trace_schema import TraceArtifact, normalize_trace_artifact


@dataclass(frozen=True)
class ScenarioRun:
    scenario: HarnessScenario
    result: ChatResult
    grade: ScenarioGrade
    artifact: TraceArtifact


class ScenarioRunner:
    def __init__(self, client: AgentHarnessClient):
        self.client = client

    async def run(self, scenario: HarnessScenario) -> ScenarioRun:
        await self.client.auth_dev()
        pet_ids_by_name: dict[str, str] = {}
        for pet in scenario.pets:
            created = await self.client.create_pet(pet.name, pet.species)
            if isinstance(created, dict) and created.get("id"):
                pet_ids_by_name[pet.name] = str(created["id"])

        for event in scenario.events:
            pet_id = pet_ids_by_name.get(event.pet_name)
            if not pet_id:
                continue
            event_date = _resolve_fixture_date(event.event_date)
            await self.client.create_event(
                pet_id=pet_id,
                event_date=event_date,
                title=event.title,
                category=event.category,
                raw_text=event.raw_text,
            )

        result = ChatResult(error="scenario had no messages")
        results: list[ChatResult] = []
        for message in scenario.messages:
            result = await self.client.chat(message, language=scenario.language)
            results.append(result)
        if results:
            result = _combine_chat_results(results)

        grade = grade_result(scenario, result)
        confirm_reasons = await self._auto_confirm(scenario, result)
        side_effect_reasons = await self._grade_side_effects(scenario)
        if confirm_reasons or side_effect_reasons:
            grade = ScenarioGrade(
                scenario_id=grade.scenario_id,
                passed=False,
                reasons=[*grade.reasons, *confirm_reasons, *side_effect_reasons],
            )
        artifact = normalize_trace_artifact(
            scenario_id=scenario.id,
            user_email=self.client.email,
            input_messages=scenario.messages,
            result=result,
        )
        return ScenarioRun(
            scenario=scenario,
            result=result,
            grade=grade,
            artifact=artifact,
        )

    async def _auto_confirm(self, scenario: HarnessScenario, result: ChatResult) -> list[str]:
        if not scenario.auto_confirm:
            return []

        confirm_cards = result.all_cards("confirm_action")
        if not confirm_cards:
            return ["auto_confirm requested but no confirm_action card was returned"]

        reasons = []
        for card in confirm_cards:
            action_id = card.get("action_id")
            if not action_id:
                reasons.append("confirm_action card missing action_id")
                continue
            response = await self.client.confirm_action(str(action_id))
            if not response.get("success", True):
                reasons.append(f"confirm_action failed: {response}")
        return reasons

    async def _grade_side_effects(self, scenario: HarnessScenario) -> list[str]:
        expected = scenario.expect.side_effects
        events = None
        pets = None
        if expected.events:
            events = await self.client.get_events()
        if expected.pets:
            pets = await self.client.get_pets()
        return grade_side_effects(scenario, events=events, pets=pets)


def _resolve_fixture_date(value: str) -> str:
    if value == "today":
        return date.today().isoformat()
    if value == "yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    if value == "tomorrow":
        return (date.today() + timedelta(days=1)).isoformat()
    return value


def _combine_chat_results(results: list[ChatResult]) -> ChatResult:
    if len(results) == 1:
        return results[0]

    trace_events = []
    trace_steps = []
    trace_rounds = []
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    has_trace = False

    for result in results:
        trace = result.trace or {}
        if trace:
            has_trace = True
        trace_events.extend(trace.get("events") or [])
        trace_steps.extend(trace.get("steps") or [])
        trace_rounds.extend(trace.get("llm_rounds") or [])
        prompt_tokens += int(trace.get("total_prompt_tokens") or 0)
        completion_tokens += int(trace.get("total_completion_tokens") or 0)
        total_tokens += int(trace.get("total_tokens") or 0)

    trace = None
    if has_trace:
        trace = {
            "events": trace_events,
            "steps": trace_steps,
            "llm_rounds": trace_rounds,
            "total_prompt_tokens": prompt_tokens,
            "total_completion_tokens": completion_tokens,
            "total_tokens": total_tokens or prompt_tokens + completion_tokens,
        }

    return ChatResult(
        text="\n".join(result.text for result in results if result.text),
        cards=[card for result in results for card in result.cards],
        emergency=next((result.emergency for result in reversed(results) if result.emergency), None),
        session_id=next((result.session_id for result in reversed(results) if result.session_id), None),
        raw_events=[event for result in results for event in result.raw_events],
        elapsed_ms=sum(result.elapsed_ms for result in results),
        error="; ".join(result.error for result in results if result.error) or None,
        trace=trace,
    )
