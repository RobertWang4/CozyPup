"""LiteLLM-compatible tool definitions and execution logic for the Chat Agent."""

import json
import logging
import uuid
from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CalendarEvent, EventCategory, EventSource, EventType,
    Pet, Reminder, Species,
)

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
    {
        "type": "function",
        "function": {
            "name": "create_pet",
            "description": (
                "Create a new pet profile for the user. Use this when the user says they "
                "have a new pet and wants to add it to their account."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The pet's name."},
                    "species": {"type": "string", "enum": ["dog", "cat", "other"], "description": "The type of animal."},
                    "breed": {"type": "string", "description": "Breed, e.g. 'Golden Retriever'. Empty string if unknown."},
                    "birthday": {"type": "string", "description": "Optional birthday in YYYY-MM-DD format."},
                    "weight": {"type": "number", "description": "Optional weight in kg."},
                    "gender": {"type": "string", "enum": ["male", "female", "unknown"], "description": "Optional gender."},
                    "neutered": {"type": "boolean", "description": "Optional neutered/spayed status."},
                    "coat_color": {"type": "string", "description": "Optional coat color."},
                },
                "required": ["name", "species"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_pet_profile",
            "description": (
                "Save any information about a pet to its profile. Use this whenever the user "
                "mentions ANY detail about their pet — gender, diet, allergies, vet, weight, "
                "temperament, medical history, etc. The info is stored as flexible key-value pairs. "
                "Call this proactively to build up the pet's profile over time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet.",
                    },
                    "info": {
                        "type": "object",
                        "description": (
                            "Key-value pairs of pet info to save. Any keys are allowed. "
                            "Examples: {\"gender\": \"male\", \"weight_kg\": 5.2, \"allergies\": [\"chicken\"], "
                            "\"diet\": \"Royal Canin 200g 2x/day\", \"neutered\": true, \"vet\": \"瑞鹏医院\", "
                            "\"temperament\": \"friendly but anxious\", \"coat_color\": \"golden\"}"
                        ),
                    },
                },
                "required": ["pet_id", "info"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pets",
            "description": (
                "List all of the user's registered pets with their profiles. "
                "Use this when the user asks about their pets, wants to see all pets, "
                "or you need to look up pet IDs."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": (
                "Create a reminder that will send a push notification at the specified time. "
                "Use this when the user asks to be reminded about something — medication, "
                "vet appointments, feeding schedules, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet this reminder is for.",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["medication", "vaccine", "checkup", "feeding", "grooming", "other"],
                        "description": "Type of reminder.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Short reminder title, e.g. 'Give heartworm medication'.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional detailed description.",
                    },
                    "trigger_at": {
                        "type": "string",
                        "description": "When to send the reminder, in ISO 8601 format (YYYY-MM-DDTHH:MM:SS).",
                    },
                },
                "required": ["pet_id", "type", "title", "trigger_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_places",
            "description": (
                "Search for nearby pet-related places like veterinary clinics, pet stores, "
                "dog parks, groomers, or emergency animal hospitals. Use when the user asks "
                "to find a location or asks 'where can I...'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search query for Google Places, e.g. 'veterinary clinic', "
                            "'dog park', '24 hour emergency vet'."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_email",
            "description": (
                "Present a draft email as a card for the user to review and send. "
                "Use when the user asks to compose an email to a vet or pet professional. "
                "YOU write the email content based on conversation context, then call this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "Email subject line.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Full email body text.",
                    },
                },
                "required": ["subject", "body"],
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

    # Verify pet belongs to user
    pet_result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = pet_result.scalar_one_or_none()
    if not pet:
        return {"success": False, "error": "Pet not found"}

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
        "pet_name": pet.name,
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


PET_COLORS = ["E8835C", "6BA3BE", "7BAE7F", "9B7ED8", "E8A33C"]


async def _create_pet(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Create a new pet profile."""
    name = arguments["name"]
    species = Species(arguments["species"])
    breed = arguments.get("breed", "")
    birthday_str = arguments.get("birthday")
    weight = arguments.get("weight")

    # Auto-assign color
    count_result = await db.execute(
        select(func.count()).where(Pet.user_id == user_id)
    )
    count = count_result.scalar() or 0
    color = PET_COLORS[count % len(PET_COLORS)]

    pet = Pet(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        species=species,
        breed=breed,
        birthday=date.fromisoformat(birthday_str) if birthday_str else None,
        weight=weight,
        color_hex=color,
    )

    # Store optional fields in flexible profile JSON
    profile = {}
    for key in ("gender", "neutered", "coat_color"):
        if key in arguments:
            profile[key] = arguments[key]
    if profile:
        pet.profile = profile

    db.add(pet)
    await db.flush()

    card = {
        "type": "pet_created",
        "pet_name": name,
        "species": arguments["species"],
        "breed": breed,
    }

    return {
        "success": True,
        "pet_id": str(pet.id),
        "pet_name": name,
        "species": arguments["species"],
        "card": card,
    }


async def _update_pet_profile(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Merge new info into the pet's flexible JSON profile."""
    pet_id = uuid.UUID(arguments["pet_id"])
    info = arguments.get("info", {})
    if not info:
        return {"success": False, "error": "No info provided"}

    result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        return {"success": False, "error": "Pet not found"}

    # Also update real columns if matching keys are provided
    if "birthday" in info:
        try:
            pet.birthday = date.fromisoformat(str(info["birthday"]))
        except (ValueError, TypeError):
            pass
    if "weight" in info or "weight_kg" in info:
        w = info.get("weight") or info.get("weight_kg")
        if isinstance(w, (int, float)):
            pet.weight = float(w)
    if "name" in info:
        pet.name = str(info["name"])
    if "breed" in info:
        pet.breed = str(info["breed"])

    # Merge into flexible JSON profile
    existing = dict(pet.profile) if pet.profile else {}
    existing.update(info)
    pet.profile = existing

    await db.flush()

    return {
        "success": True,
        "pet_id": str(pet.id),
        "pet_name": pet.name,
        "saved_keys": list(info.keys()),
    }


async def _list_pets(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """List all pets for the user."""
    result = await db.execute(
        select(Pet).where(Pet.user_id == user_id).order_by(Pet.created_at)
    )
    pets = result.scalars().all()

    return {
        "pets": [
            {
                "id": str(p.id),
                "name": p.name,
                "species": p.species.value,
                "breed": p.breed,
                "birthday": p.birthday.isoformat() if p.birthday else None,
                "weight": p.weight,
                "profile": p.profile or {},
            }
            for p in pets
        ],
        "count": len(pets),
    }


async def _create_reminder(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Create a reminder for push notification."""
    pet_id = uuid.UUID(arguments["pet_id"])

    # Verify pet belongs to user
    pet_result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = pet_result.scalar_one_or_none()
    if not pet:
        return {"success": False, "error": "Pet not found"}

    reminder = Reminder(
        id=uuid.uuid4(),
        user_id=user_id,
        pet_id=pet_id,
        type=arguments["type"],
        title=arguments["title"],
        body=arguments.get("body", ""),
        trigger_at=datetime.fromisoformat(arguments["trigger_at"]),
    )
    db.add(reminder)
    await db.flush()

    card = {
        "type": "reminder",
        "pet_name": pet.name,
        "title": arguments["title"],
        "trigger_at": arguments["trigger_at"],
        "reminder_type": arguments["type"],
    }

    return {
        "success": True,
        "reminder_id": str(reminder.id),
        "title": arguments["title"],
        "trigger_at": arguments["trigger_at"],
        "card": card,
    }


async def _search_places(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    location: dict | None = None,
    **_kwargs,
) -> dict:
    """Search for nearby places via Google Places API."""
    if not location or "lat" not in location or "lng" not in location:
        return {
            "success": False,
            "error": "No location available. Ask the user to share their location.",
        }

    from app.services.places import places_service  # lazy import

    query = arguments["query"]
    places = await places_service.search_nearby(
        lat=location["lat"], lng=location["lng"], query=query
    )

    if not places:
        return {
            "success": True,
            "places": [],
            "message": f"No results found for '{query}' nearby.",
        }

    card = {
        "type": "map",
        "query": query,
        "places": [
            {
                "name": p["name"],
                "address": p["address"],
                "rating": p.get("rating"),
                "lat": p["lat"],
                "lng": p["lng"],
            }
            for p in places
        ],
    }

    return {
        "success": True,
        "places_count": len(places),
        "top_results": [f"{p['name']} — {p['address']}" for p in places[:5]],
        "card": card,
    }


async def _draft_email(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Wrap an email draft into a card for the frontend."""
    subject = arguments["subject"]
    body = arguments["body"]

    card = {
        "type": "email",
        "subject": subject,
        "body": body,
    }

    return {
        "success": True,
        "card": card,
    }


_TOOL_HANDLERS = {
    "create_calendar_event": _create_calendar_event,
    "query_calendar_events": _query_calendar_events,
    "create_pet": _create_pet,
    "update_pet_profile": _update_pet_profile,
    "list_pets": _list_pets,
    "create_reminder": _create_reminder,
    "search_places": _search_places,
    "draft_email": _draft_email,
}

# Tools that accept extra kwargs (e.g., location)
_TOOLS_WITH_KWARGS = {"search_places"}


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
