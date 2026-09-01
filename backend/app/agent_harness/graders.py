"""Deterministic graders for agent harness scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field

from .client import ChatResult, get_tools_called
from .scenario import EventSideEffect, HarnessScenario, PetSideEffect


@dataclass(frozen=True)
class ScenarioGrade:
    scenario_id: str
    passed: bool
    reasons: list[str] = field(default_factory=list)


def grade_result(scenario: HarnessScenario, result: ChatResult) -> ScenarioGrade:
    reasons: list[str] = []
    tools = get_tools_called(result)
    card_types = [card.get("type") for card in result.cards]
    text = _gradeable_text(result)

    for tool in scenario.expect.tools:
        if tool not in tools:
            reasons.append(f"missing tool: {tool}")

    for tool in scenario.expect.forbidden_tools:
        if tool in tools:
            reasons.append(f"forbidden tool called: {tool}")

    for card_type in scenario.expect.cards:
        if card_type not in card_types:
            reasons.append(f"missing card: {card_type}")

    if scenario.expect.contains_any and not any(item in text for item in scenario.expect.contains_any):
        reasons.append(f"missing any text: {scenario.expect.contains_any}")

    for item in scenario.expect.contains_all:
        if item not in text:
            reasons.append(f"missing text: {item}")

    if scenario.expect.max_latency_ms is not None and result.elapsed_ms > scenario.expect.max_latency_ms:
        reasons.append(f"latency {result.elapsed_ms}ms exceeded {scenario.expect.max_latency_ms}ms")

    if scenario.expect.emergency is True and not result.emergency:
        reasons.append("missing emergency event")
    if scenario.expect.emergency is False and result.emergency:
        reasons.append("unexpected emergency event")

    if result.error:
        reasons.append(f"client error: {result.error}")

    return ScenarioGrade(
        scenario_id=scenario.id,
        passed=not reasons,
        reasons=reasons,
    )


def grade_side_effects(
    scenario: HarnessScenario,
    *,
    events: list[dict] | None = None,
    pets: list[dict] | None = None,
) -> list[str]:
    reasons: list[str] = []
    events = events or []
    pets = pets or []

    for expected in scenario.expect.side_effects.events:
        if not any(_event_matches(expected, event) for event in events):
            reasons.append(f"missing event side effect: {_describe_event_expectation(expected)}")

    for expected in scenario.expect.side_effects.pets:
        if not any(_pet_matches(expected, pet) for pet in pets):
            reasons.append(f"missing pet side effect: {_describe_pet_expectation(expected)}")

    return reasons


def _contains_any(text: str, needles: list[str]) -> bool:
    if not needles:
        return True
    lower = text.lower()
    return any(needle.lower() in lower for needle in needles)


def _gradeable_text(result: ChatResult) -> str:
    parts = [result.text or ""]
    if result.emergency and result.emergency.get("message"):
        parts.append(str(result.emergency["message"]))
    for card in result.cards:
        if card.get("message"):
            parts.append(str(card["message"]))
    return "\n".join(parts)


def _contains_all(text: str, needles: list[str]) -> bool:
    lower = text.lower()
    return all(needle.lower() in lower for needle in needles)


def _event_matches(expected: EventSideEffect, event: dict) -> bool:
    if expected.pet_name and expected.pet_name not in str(event.get("pet_name", "")):
        return False
    if expected.category and event.get("category") != expected.category:
        return False
    title = str(event.get("title", ""))
    if not _contains_any(title, expected.title_contains_any):
        return False
    if not _contains_all(title, expected.title_contains_all):
        return False
    if expected.reminder_required is not None:
        has_reminder = bool(event.get("reminder_at"))
        if has_reminder != expected.reminder_required:
            return False
    if expected.cost is not None and event.get("cost") != expected.cost:
        return False
    return True


def _pet_matches(expected: PetSideEffect, pet: dict) -> bool:
    if pet.get("name") != expected.name:
        return False
    if expected.species and pet.get("species") != expected.species:
        return False
    if expected.weight is not None and pet.get("weight") != expected.weight:
        return False
    profile_md = str(pet.get("profile_md", ""))
    if not _contains_any(profile_md, expected.profile_md_contains_any):
        return False
    if not _contains_all(profile_md, expected.profile_md_contains_all):
        return False
    return True


def _describe_event_expectation(expected: EventSideEffect) -> str:
    parts = []
    if expected.pet_name:
        parts.append(f"pet_name={expected.pet_name}")
    if expected.category:
        parts.append(f"category={expected.category}")
    if expected.title_contains_any:
        parts.append(f"title_contains_any={expected.title_contains_any}")
    if expected.reminder_required is not None:
        parts.append(f"reminder_required={expected.reminder_required}")
    return ", ".join(parts) or "event"


def _describe_pet_expectation(expected: PetSideEffect) -> str:
    parts = [f"name={expected.name}"]
    if expected.species:
        parts.append(f"species={expected.species}")
    if expected.weight is not None:
        parts.append(f"weight={expected.weight}")
    if expected.profile_md_contains_any:
        parts.append(f"profile_md_contains_any={expected.profile_md_contains_any}")
    return ", ".join(parts)
