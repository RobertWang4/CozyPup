"""Tools package — schema definitions + dispatch entry point.

Importing this package imports every domain module (calendar, pets,
reminders, misc, tasks, knowledge), which triggers the `@register_tool`
decorators and populates the registry. `execute_tool` then looks up the
handler by name.

Re-exports individual handler functions for back-compat with call sites
that imported them directly before the registry existed.
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.definitions import (
    TOOL_DEFINITIONS,
    _BASE_TOOL_DEFINITIONS,
    _tool_defs_cache,
    get_tool_definitions,
)

# Import domain modules to trigger @register_tool decorators
import app.agents.tools.calendar  # noqa: F401
import app.agents.tools.pets      # noqa: F401
import app.agents.tools.reminders # noqa: F401
import app.agents.tools.misc      # noqa: F401
import app.agents.tools.tasks     # noqa: F401
import app.agents.tools.knowledge  # noqa: F401
import app.agents.tools.schedule  # noqa: F401

from app.agents.tools.registry import get_registered_tools

# Re-export individual handlers so existing imports keep working
from app.agents.tools.calendar import (
    create_calendar_event,
    delete_calendar_event,
    query_calendar_events,
    remove_event_photo,
    update_calendar_event,
    upload_event_photo,
)
from app.agents.tools.knowledge import search_knowledge
from app.agents.tools.schedule import get_deworming_schedule, get_vaccine_schedule
from app.agents.tools.misc import (
    draft_email,
    get_directions_tool,
    get_place_details_tool,
    search_places,
    set_language,
    trigger_emergency,
)
from app.agents.tools.pets import (
    create_pet,
    delete_pet,
    list_pets,
    save_pet_profile_md,
    set_pet_avatar,
    summarize_pet_profile,
    update_pet_profile,
    verify_pet_ownership,
)
from app.agents.tools.reminders import (
    create_reminder,
    delete_all_reminders,
    delete_reminder,
    list_reminders,
    update_reminder,
)

logger = logging.getLogger(__name__)

__all__ = [
    "TOOL_DEFINITIONS",
    "_BASE_TOOL_DEFINITIONS",
    "_tool_defs_cache",
    "get_tool_definitions",
    "execute_tool",
    # calendar
    "create_calendar_event",
    "query_calendar_events",
    "update_calendar_event",
    "delete_calendar_event",
    "upload_event_photo",
    "remove_event_photo",
    # pets
    "create_pet",
    "update_pet_profile",
    "save_pet_profile_md",
    "summarize_pet_profile",
    "list_pets",
    "delete_pet",
    "set_pet_avatar",
    "verify_pet_ownership",
    # reminders
    "create_reminder",
    "list_reminders",
    "update_reminder",
    "delete_reminder",
    "delete_all_reminders",
    # misc
    "search_places",
    "draft_email",
    "set_language",
    "trigger_emergency",
    "get_place_details_tool",
    "get_directions_tool",
    # knowledge
    "search_knowledge",
    # schedule
    "get_vaccine_schedule",
    "get_deworming_schedule",
]


async def execute_tool(
    name: str,
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    **kwargs,
) -> dict:
    """Look up and call the registered handler for `name`.

    Raises ValueError if the tool isn't registered (including
    `request_images`, which must be handled by the orchestrator because
    it needs to mutate the message list, not return a tool result).
    Re-raises handler exceptions after logging.
    """
    registry = get_registered_tools()
    entry = registry.get(name)
    if entry is None:
        if name == "request_images":
            raise ValueError("request_images is handled by orchestrator, not execute_tool")
        raise ValueError(f"Unknown tool: {name}")

    handler = entry["handler"]
    logger.info("tool_execute", extra={"tool": name, "arguments_keys": list(arguments.keys())})
    try:
        if entry["accepts_kwargs"]:
            result = await handler(arguments, db, user_id, **kwargs)
        else:
            result = await handler(arguments, db, user_id)
        logger.info("tool_success", extra={"tool": name})
        return result
    except Exception as exc:
        logger.error("tool_error", extra={"tool": name, "error": str(exc)[:200]})
        raise
