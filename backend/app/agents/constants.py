"""Shared constants for the agent pipeline."""

import asyncio

# Destructive tools that always require user confirmation via confirm card.
CONFIRM_TOOLS = {
    "delete_pet",
    "delete_calendar_event",
    "delete_reminder",
    "delete_all_reminders",
}

# Tools whose confirmation depends on the action argument.
# Maps tool name → set of actions that trigger confirmation.
CONDITIONAL_CONFIRM_ACTIONS = {
    "manage_daily_task": {"delete", "delete_all", "deactivate"},
}


def needs_confirm(fn_name: str, fn_args: dict) -> bool:
    """Return True if this tool call requires a confirm card before executing."""
    if fn_name in CONFIRM_TOOLS:
        return True
    actions = CONDITIONAL_CONFIRM_ACTIONS.get(fn_name)
    if actions and fn_args.get("action") in actions:
        return True
    return False

# Tools that the LLM frequently forgets to call — nudge and post-processor
# will only force these. All other pre-processor suggestions are advisory only.
NUDGE_TOOLS = {"search_places", "trigger_emergency", "set_language"}

# Tools whose results are simple enough to skip the Round 2 LLM call.
# After successful execution, we use the LLM's streaming text from Round 1
# (or a minimal fallback) instead of feeding the result back for another LLM turn.
# This saves ~8000 prompt tokens per skipped round.
#
# NOT in this set (require LLM to interpret results):
#   query_calendar_events, search_places, get_place_details, get_directions,
#   trigger_emergency, search_knowledge, list_reminders, draft_email,
#   summarize_pet_profile, list_pets
# Also excluded: plan, request_images (need continued loop execution)
SKIP_ROUND2_TOOLS = {
    "create_calendar_event",
    "create_pet",
    "update_pet_profile",
    "update_calendar_event",
    "delete_calendar_event",
    "delete_pet",
    "create_reminder",
    "update_reminder",
    "delete_reminder",
    "delete_all_reminders",
    "set_language",
    "set_pet_avatar",
    "upload_event_photo",
    "save_pet_profile_md",
    "manage_daily_task",
    "create_daily_task",
    "add_event_location",
    "remove_event_photo",
    "introduce_product",
}


async def maybe_await(fn, *args):
    """Call fn(*args), awaiting the result if it's a coroutine."""
    result = fn(*args)
    if asyncio.iscoroutine(result):
        return await result
    return result
