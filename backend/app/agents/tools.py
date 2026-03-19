"""LiteLLM-compatible tool definitions and execution logic for the Chat Agent."""

import json
import logging
import uuid
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CalendarEvent, EventCategory, EventSource, EventType, Pet

logger = logging.getLogger(__name__)

# ---------- Tool Definitions (OpenAI function calling format) ----------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": (
                "Record a pet health event to the calendar. Use this when the user mentions "
                "feeding, symptoms, medications, vaccinations, deworming, vet visits, or any "
                "daily care activity that should be logged."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet this event is for.",
                    },
                    "event_date": {
                        "type": "string",
                        "description": "Date of the event in YYYY-MM-DD format.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Short description of the event, e.g. 'Fed 200g kibble' or 'Vomited twice'.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"],
                        "description": "Category of the health event.",
                    },
                    "event_time": {
                        "type": "string",
                        "description": "Optional time in HH:MM format.",
                    },
                    "raw_text": {
                        "type": "string",
                        "description": "Optional original user text that triggered this record.",
                    },
                },
                "required": ["pet_id", "event_date", "title", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_calendar_events",
            "description": (
                "Query the pet's calendar event history. Use this when the user asks about "
                "past events, health history, or wants to review what was logged."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "Optional UUID of the pet to filter by.",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Optional start date in YYYY-MM-DD format.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Optional end date in YYYY-MM-DD format.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"],
                        "description": "Optional category filter.",
                    },
                },
                "required": [],
            },
        },
    },
]


# ---------- Tool Execution ----------


async def _create_calendar_event(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Create a CalendarEvent record in the database."""
    pet_id = uuid.UUID(arguments["pet_id"])
    event_date = date.fromisoformat(arguments["event_date"])
    title = arguments["title"]
    category = EventCategory(arguments["category"])
    event_time_str = arguments.get("event_time")
    raw_text = arguments.get("raw_text", "")

    event_time = None
    if event_time_str:
        parts = event_time_str.split(":")
        event_time = time(int(parts[0]), int(parts[1]))

    # Look up pet name for card data
    pet_result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = pet_result.scalar_one_or_none()
    pet_name = pet.name if pet else "Unknown"

    event = CalendarEvent(
        user_id=user_id,
        pet_id=pet_id,
        event_date=event_date,
        event_time=event_time,
        title=title,
        type=EventType.log,
        category=category,
        raw_text=raw_text,
        source=EventSource.chat,
        edited=False,
    )
    db.add(event)
    await db.flush()

    card = {
        "type": "record",
        "pet_name": pet_name,
        "date": arguments["event_date"],
        "category": arguments["category"],
        "title": title,
    }

    return {
        "success": True,
        "event_id": str(event.id),
        "title": title,
        "category": arguments["category"],
        "event_date": arguments["event_date"],
        "card": card,
    }


async def _query_calendar_events(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Query CalendarEvent records from the database."""
    query = select(CalendarEvent).where(CalendarEvent.user_id == user_id)

    if arguments.get("pet_id"):
        query = query.where(CalendarEvent.pet_id == uuid.UUID(arguments["pet_id"]))
    if arguments.get("start_date"):
        query = query.where(CalendarEvent.event_date >= date.fromisoformat(arguments["start_date"]))
    if arguments.get("end_date"):
        query = query.where(CalendarEvent.event_date <= date.fromisoformat(arguments["end_date"]))
    if arguments.get("category"):
        query = query.where(CalendarEvent.category == EventCategory(arguments["category"]))

    query = query.order_by(CalendarEvent.event_date.desc()).limit(50)
    result = await db.execute(query)
    events = result.scalars().all()

    return {
        "events": [
            {
                "id": str(e.id),
                "pet_id": str(e.pet_id),
                "event_date": e.event_date.isoformat(),
                "event_time": e.event_time.isoformat() if e.event_time else None,
                "title": e.title,
                "category": e.category.value,
                "raw_text": e.raw_text,
                "source": e.source.value,
            }
            for e in events
        ],
        "count": len(events),
    }


_TOOL_HANDLERS = {
    "create_calendar_event": _create_calendar_event,
    "query_calendar_events": _query_calendar_events,
}


async def execute_tool(
    name: str,
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Dispatch a tool call to the appropriate handler.

    Args:
        name: The tool function name.
        arguments: The parsed arguments dict from the LLM.
        db: An async database session.
        user_id: The authenticated user's UUID.

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
        result = await handler(arguments, db, user_id)
        logger.info("tool_success", extra={"tool": name})
        return result
    except Exception as exc:
        logger.error("tool_error", extra={"tool": name, "error": str(exc)[:200]})
        raise
