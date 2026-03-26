"""Shared constants for the agent pipeline."""

import asyncio

# Only destructive tools require user confirmation via confirm card.
CONFIRM_TOOLS = {"delete_pet", "delete_calendar_event", "delete_reminder"}


async def maybe_await(fn, *args):
    """Call fn(*args), awaiting the result if it's a coroutine."""
    result = fn(*args)
    if asyncio.iscoroutine(result):
        return await result
    return result
