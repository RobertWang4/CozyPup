"""Scenario file schema for deterministic agent harness evals."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PetFixture:
    name: str
    species: str = "dog"


@dataclass(frozen=True)
class EventFixture:
    pet_name: str
    event_date: str = "today"
    title: str = ""
    category: str = "daily"
    raw_text: str = ""


@dataclass(frozen=True)
class EventSideEffect:
    pet_name: str | None = None
    category: str | None = None
    title_contains_any: list[str] = field(default_factory=list)
    title_contains_all: list[str] = field(default_factory=list)
    reminder_required: bool | None = None
    cost: float | None = None


@dataclass(frozen=True)
class PetSideEffect:
    name: str
    species: str | None = None
    weight: float | None = None
    profile_md_contains_any: list[str] = field(default_factory=list)
    profile_md_contains_all: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SideEffectExpectations:
    events: list[EventSideEffect] = field(default_factory=list)
    pets: list[PetSideEffect] = field(default_factory=list)
    absent_events: list[EventSideEffect] = field(default_factory=list)


@dataclass(frozen=True)
class ExpectedOutcome:
    tools: list[str] = field(default_factory=list)
    tools_executed: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    cards: list[str] = field(default_factory=list)
    forbidden_cards: list[str] = field(default_factory=list)
    judge: list[str] = field(default_factory=list)
    contains_any: list[str] = field(default_factory=list)
    contains_all: list[str] = field(default_factory=list)
    max_latency_ms: int | None = None
    emergency: bool | None = None
    side_effects: SideEffectExpectations = field(default_factory=SideEffectExpectations)


@dataclass(frozen=True)
class HarnessScenario:
    id: str
    description: str
    messages: list[str]
    language: str | None = None
    auto_confirm: bool = False
    pets: list[PetFixture] = field(default_factory=list)
    events: list[EventFixture] = field(default_factory=list)
    expect: ExpectedOutcome = field(default_factory=ExpectedOutcome)


def _event_side_effect(item: dict) -> EventSideEffect:
    return EventSideEffect(
        pet_name=item.get("pet_name"),
        category=item.get("category"),
        title_contains_any=list(item.get("title_contains_any", [])),
        title_contains_all=list(item.get("title_contains_all", [])),
        reminder_required=item.get("reminder_required"),
        cost=item.get("cost"),
    )


def load_scenario(path: str | Path) -> HarnessScenario:
    data = json.loads(Path(path).read_text())
    expect = data.get("expect", {})
    side_effects = expect.get("side_effects", {})
    return HarnessScenario(
        id=str(data["id"]),
        description=str(data.get("description", "")),
        language=data.get("language"),
        auto_confirm=bool(data.get("auto_confirm", False)),
        messages=[str(item) for item in data.get("messages", [])],
        pets=[
            PetFixture(name=str(pet["name"]), species=str(pet.get("species", "dog")))
            for pet in data.get("pets", [])
        ],
        events=[
            EventFixture(
                pet_name=str(event["pet_name"]),
                event_date=str(event.get("event_date", "today")),
                title=str(event.get("title", "")),
                category=str(event.get("category", "daily")),
                raw_text=str(event.get("raw_text", "")),
            )
            for event in data.get("events", [])
        ],
        expect=ExpectedOutcome(
            tools=list(expect.get("tools", [])),
            tools_executed=list(expect.get("tools_executed", [])),
            forbidden_tools=list(expect.get("forbidden_tools", [])),
            cards=list(expect.get("cards", [])),
            forbidden_cards=list(expect.get("forbidden_cards", [])),
            judge=[str(item) for item in expect.get("judge", [])],
            contains_any=list(expect.get("contains_any", [])),
            contains_all=list(expect.get("contains_all", [])),
            max_latency_ms=expect.get("max_latency_ms"),
            emergency=expect.get("emergency"),
            side_effects=SideEffectExpectations(
                events=[_event_side_effect(item) for item in side_effects.get("events", [])],
                absent_events=[
                    _event_side_effect(item) for item in side_effects.get("absent_events", [])
                ],
                pets=[
                    PetSideEffect(
                        name=str(item["name"]),
                        species=item.get("species"),
                        weight=item.get("weight"),
                        profile_md_contains_any=list(item.get("profile_md_contains_any", [])),
                        profile_md_contains_all=list(item.get("profile_md_contains_all", [])),
                    )
                    for item in side_effects.get("pets", [])
                ],
            ),
        ),
    )
