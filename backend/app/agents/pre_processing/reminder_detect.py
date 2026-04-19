"""Reminder intent detection.

Triggers on "remind me", "别忘了", "记得" patterns. Not blocked by the
question-override heuristic because reminders are inherently future-
looking even when phrased as questions ("should you remind me to...").
"""

import re
from datetime import date, datetime

from app.agents.locale import t
from .types import SuggestedAction
from .date_utils import resolve_date
from .pet_utils import resolve_pets


_REMINDER_PATTERNS = [
    (re.compile(r"提醒我|别忘了|记得|remind me|don't forget|set.*reminder", re.I), 0.85),
]

_REMINDER_TYPES_MAP = [
    (re.compile(r"喂药|吃药|medication|medicine", re.I), "medication"),
    (re.compile(r"疫苗|打针|vaccin", re.I), "vaccine"),
    (re.compile(r"体检|检查|checkup", re.I), "checkup"),
    (re.compile(r"喂食|喂饭|feeding|feed", re.I), "feeding"),
    (re.compile(r"洗澡|美容|grooming|groom|bath", re.I), "grooming"),
]


def detect(
    message: str,
    pets: list,
    today: date,
    lang: str,
) -> list[SuggestedAction]:
    """Detect reminder intents and return suggested actions."""
    actions: list[SuggestedAction] = []

    # Reminder patterns should NOT be blocked by is_question (reminders are future actions)
    for pattern, confidence in _REMINDER_PATTERNS:
        if pattern.search(message):
            # Infer reminder type
            reminder_type = "other"
            for type_pattern, type_name in _REMINDER_TYPES_MAP:
                if type_pattern.search(message):
                    reminder_type = type_name
                    break

            trigger_date = resolve_date(message, today)
            trigger_at = datetime.combine(trigger_date, datetime.min.replace(hour=9).time()).isoformat()

            resolved_pets = resolve_pets(message, pets) if pets else []

            if resolved_pets:
                for pet_id, pet_name in resolved_pets:
                    actions.append(SuggestedAction(
                        tool_name="create_reminder",
                        arguments={
                            "pet_id": pet_id,
                            "title": message[:100],
                            "type": reminder_type,
                            "trigger_at": trigger_at,
                        },
                        confidence=confidence,
                        confirm_description=t("confirm_reminder_for_pet", lang).format(pet_name=pet_name, type=reminder_type, date=trigger_date.isoformat()),
                    ))
            else:
                actions.append(SuggestedAction(
                    tool_name="create_reminder",
                    arguments={
                        "title": message[:100],
                        "type": reminder_type,
                        "trigger_at": trigger_at,
                    },
                    confidence=confidence,
                    confirm_description=t("confirm_reminder", lang).format(type=reminder_type, date=trigger_date.isoformat()),
                ))
            break  # Only match first reminder pattern

    return actions
