"""Agent tools package — public API."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.calendar import (
    create_calendar_event,
    delete_calendar_event,
    query_calendar_events,
    update_calendar_event,
    upload_event_photo,
)
from app.agents.tools.definitions import (
    TOOL_DEFINITIONS,
    _BASE_TOOL_DEFINITIONS,
    _tool_defs_cache,
    get_tool_definitions,
)
from app.agents.tools.misc import (
    draft_email,
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
    delete_reminder,
    list_reminders,
    update_reminder,
)

__all__ = [
    "execute_tool",
    "get_tool_definitions",
    "TOOL_DEFINITIONS",
    "_BASE_TOOL_DEFINITIONS",
    "_tool_defs_cache",
    # calendar
    "create_calendar_event",
    "query_calendar_events",
    "update_calendar_event",
    "delete_calendar_event",
    "upload_event_photo",
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
    # misc
    "search_places",
    "draft_email",
    "set_language",
    "trigger_emergency",
]

logger = logging.getLogger(__name__)

_TOOL_HANDLERS = {
    "create_calendar_event": create_calendar_event,
    "query_calendar_events": query_calendar_events,
    "update_calendar_event": update_calendar_event,
    "create_pet": create_pet,
    "update_pet_profile": update_pet_profile,
    "save_pet_profile_md": save_pet_profile_md,
    "summarize_pet_profile": summarize_pet_profile,
    "list_pets": list_pets,
    "create_reminder": create_reminder,
    "search_places": search_places,
    "draft_email": draft_email,
    "delete_pet": delete_pet,
    "delete_calendar_event": delete_calendar_event,
    "list_reminders": list_reminders,
    "update_reminder": update_reminder,
    "delete_reminder": delete_reminder,
    "upload_event_photo": upload_event_photo,
    "set_language": set_language,
    "set_pet_avatar": set_pet_avatar,
    "trigger_emergency": trigger_emergency,
    "request_images": None,  # Special: handled by orchestrator, not here
}

# Tools that accept extra kwargs (e.g., location, images)
_TOOLS_WITH_KWARGS = {"search_places", "upload_event_photo", "set_pet_avatar", "create_calendar_event"}


async def execute_tool(
    name: str,
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    **kwargs,
) -> dict:
    """Dispatch a tool call to the appropriate handler.

    Args:
        name: The tool function name.
        arguments: The parsed arguments dict from the LLM.
        db: An async database session.
        user_id: The authenticated user's UUID.
        **kwargs: Extra keyword arguments forwarded only to tools in _TOOLS_WITH_KWARGS.

    Returns:
        A dict with the tool execution result.

    Raises:
        ValueError: If the tool name is unknown.
    """
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")

    logger.info("tool_execute", extra={"tool": name, "arguments_keys": list(arguments.keys())})
    try:
        if name in _TOOLS_WITH_KWARGS:
            result = await handler(arguments, db, user_id, **kwargs)
        else:
            result = await handler(arguments, db, user_id)
        logger.info("tool_success", extra={"tool": name})
        return result
    except Exception as exc:
        logger.error("tool_error", extra={"tool": name, "error": str(exc)[:200]})
        raise
