"""Main pre_process() entry point — calls all domain detectors."""

import re
from datetime import date

from .types import SuggestedAction, CONFIRM_THRESHOLD
from . import calendar_detect, pet_detect, reminder_detect, misc_detect, task_detect


_QUESTION_OVERRIDE = re.compile(
    r"[?？]|怎么|为什么|多久|多少|上次|最近|几次|哪天|什么时候"
    r"|how|when|why|what|last time|should|可以吗|能不能|要不要|是不是|好不好",
    re.I,
)

_MULTI_EVENT_SPLITTER = re.compile(
    r"还|又|以及|并且|同时|然后|和(?=.*了)|且"
    r"|and also|and then|also|as well as|plus",
    re.I,
)


def pre_process(
    message: str,
    pets: list,
    today: date | None = None,
    lang: str = "zh",
) -> list[SuggestedAction]:
    """Analyze user message and return suggested tool calls with pre-filled arguments.

    Args:
        message: The user's raw message text.
        pets: List of Pet model instances or dicts with id/name fields.
        today: Override for today's date (for testing).

    Returns:
        List of SuggestedAction. Empty if no action detected.
    """
    if today is None:
        today = date.today()

    # If the message is clearly a question, don't suggest recording actions
    is_question = bool(_QUESTION_OVERRIDE.search(message))

    actions: list[SuggestedAction] = []

    # --- Calendar events ---
    actions.extend(calendar_detect.detect(message, pets, today, lang, is_question))

    # --- Create pet ---
    actions.extend(pet_detect.detect_create_pet(message, lang))

    # --- Reminders ---
    actions.extend(reminder_detect.detect(message, pets, today, lang))

    # Daily tasks
    actions.extend(task_detect.detect(message, pets, today, lang, is_question))

    # --- Misc: search_places, draft_email, summarize_profile, set_avatar, language ---
    actions.extend(misc_detect.detect(message, pets, today, lang, is_question))

    # --- Update pet profile ---
    actions.extend(pet_detect.detect_update_profile(message, pets, is_question, lang))

    return actions
