"""Calendar event intent detection for pre-processing."""

import re
from datetime import date

from app.agents.locale import t
from .types import SuggestedAction
from .date_utils import resolve_date
from .pet_utils import resolve_pets


_CALENDAR_PATTERNS = [
    # (regex, category, confidence)
    (re.compile(r"吃了|喂了|喂食|吃的|feeding|fed|ate|kibble", re.I), "diet", 0.9),
    (re.compile(r"拉了|拉稀|拉肚子|大便|排便|excretion|poop", re.I), "excretion", 0.9),
    (re.compile(r"吐了|呕吐|vomit|不舒服|不太好|sick|异常", re.I), "abnormal", 0.9),
    (re.compile(r"打了.*疫苗|接种|vaccin", re.I), "vaccine", 0.9),
    (re.compile(r"驱虫|deworm", re.I), "deworming", 0.9),
    (re.compile(r"看医生|去医院|看兽医|vet visit|checkup|体检", re.I), "medical", 0.85),
    (re.compile(r"遛了|遛狗|散步|走了|洗澡|grooming|walk|park|公园", re.I), "daily", 0.85),
]

# Completion/status phrases — "都打完了" describes a state, not an event
# When detected, suppress calendar hint so LLM decides on its own
_STATUS_OVERRIDE = re.compile(
    r"都.*(?:打完|做完|完成|打齐|做齐)|已经.*(?:完了|完成|打完|做完)"
    r"|打完了|打齐了|做完了|完成了|做齐了"
    r"|all done|completed|finished|fully vaccinated|all.*shots.*done",
    re.I,
)


def detect(
    message: str,
    pets: list,
    today: date,
    lang: str,
    is_question: bool,
) -> list[SuggestedAction]:
    """Detect calendar event intents and return suggested actions."""
    actions: list[SuggestedAction] = []

    is_status = bool(_STATUS_OVERRIDE.search(message))
    if is_question or is_status:
        return actions

    matched_categories = []
    for pattern, category, confidence in _CALENDAR_PATTERNS:
        if pattern.search(message):
            matched_categories.append((category, confidence))

    # Deduplicate: if multiple patterns match, each gets its own event suggestion
    seen_cats = set()
    unique_matches = []
    for cat, conf in matched_categories:
        if cat not in seen_cats:
            seen_cats.add(cat)
            unique_matches.append((cat, conf))

    for category, confidence in unique_matches:
        event_date = resolve_date(message, today)
        resolved_pets = resolve_pets(message, pets)

        # Ambiguous date (e.g. "上周") → skip pre-processing, let LLM ask
        if event_date is None:
            continue

        # Check if a specific pet was mentioned by name
        mentioned_names = [
            p.name if hasattr(p, "name") else p.get("name", "")
            for p in pets
            if (p.name if hasattr(p, "name") else p.get("name", "")).lower() in message.lower()
        ]

        if mentioned_names:
            # Specific pet(s) mentioned → one event per mentioned pet
            for pet_id, pet_name in resolved_pets:
                if pet_name in mentioned_names:
                    actions.append(SuggestedAction(
                        tool_name="create_calendar_event",
                        arguments={
                            "pet_id": pet_id,
                            "event_date": event_date.isoformat(),
                            "title": message[:100],
                            "category": category,
                            "raw_text": message,
                        },
                        confidence=confidence,
                        confirm_description=t("confirm_record_for_pet", lang).format(pet_name=pet_name, category=category, date=event_date.isoformat()),
                    ))
        elif len(pets) == 1:
            # Only one pet → assign to that pet
            pet_id, pet_name = resolved_pets[0]
            actions.append(SuggestedAction(
                tool_name="create_calendar_event",
                arguments={
                    "pet_id": pet_id,
                    "event_date": event_date.isoformat(),
                    "title": message[:100],
                    "category": category,
                    "raw_text": message,
                },
                confidence=confidence,
                confirm_description=f"为{pet_name}记录 {category}（{event_date.isoformat()}）",
            ))
        else:
            # Multiple pets, none mentioned → ONE shared event, no pet_id
            actions.append(SuggestedAction(
                tool_name="create_calendar_event",
                arguments={
                    "event_date": event_date.isoformat(),
                    "title": message[:100],
                    "category": category,
                    "raw_text": message,
                },
                confidence=confidence,
                confirm_description=t("confirm_record", lang).format(category=category, date=event_date.isoformat()),
            ))

    return actions
