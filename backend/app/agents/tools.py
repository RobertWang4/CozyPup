"""LiteLLM-compatible tool definitions and execution logic for the Chat Agent."""

import asyncio
import base64
import json
import logging
import uuid
from datetime import date, datetime, time
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CalendarEvent, EventCategory, EventSource, EventType,
    Pet, Reminder, Species,
)

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads" / "avatars"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

PHOTO_DIR = Path(__file__).resolve().parent.parent / "uploads" / "photos"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

# Background task tracking — prevents garbage collection of fire-and-forget tasks
_bg_tasks: set[asyncio.Task] = set()

# ---------- Tool Definitions (OpenAI function calling format) ----------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": (
                "Record an event to the calendar. Use for pet health events, daily care, "
                "or shared owner activities (buying supplies, vet appointments, etc.). "
                "For SHARED events that apply to all pets or the owner (e.g. buying dog food, "
                "visiting pet store), call this ONCE with pet_id omitted. "
                "Do NOT create duplicate events for each pet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of a single pet. Use pet_ids for multi-pet events.",
                    },
                    "pet_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of pet UUIDs this event applies to. Use for multi-pet events "
                            "(e.g. both dogs went for a walk). OMIT for owner-only events. "
                            "If only one pet, you can use pet_id instead."
                        ),
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
                    "photo_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "URLs of photos to attach to this event (if user sent images)",
                    },
                },
                "required": ["event_date", "title", "category"],
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
            "name": "update_calendar_event",
            "description": (
                "Update an existing calendar event. Use this when the user wants to change "
                "the date, time, title, or category of a previously recorded event. "
                "You MUST first call query_calendar_events to find the event_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "UUID of the event to update (from query_calendar_events results).",
                    },
                    "event_date": {
                        "type": "string",
                        "description": "New date in YYYY-MM-DD format.",
                    },
                    "event_time": {
                        "type": "string",
                        "description": "New time in HH:MM format.",
                    },
                    "title": {
                        "type": "string",
                        "description": "New title/description.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"],
                        "description": "New category.",
                    },
                },
                "required": ["event_id"],
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
                "Update any information about a pet, including RENAMING. Use this whenever the user "
                "wants to change their pet's name, or mentions ANY detail about their pet — gender, "
                "diet, allergies, vet, weight, temperament, medical history, etc. "
                "To rename: pass {\"name\": \"new_name\"} in info. "
                "The info is stored as flexible key-value pairs. "
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
            "name": "save_pet_profile_md",
            "description": (
                "Save or update a pet's narrative profile document (markdown). "
                "Call this SILENTLY whenever you learn new information about a pet "
                "from conversation — personality, health history, routines, preferences. "
                "You MUST pass the COMPLETE updated document (not a diff or append). "
                "Keep it concise: under 500 words. Use markdown headers for sections. "
                "Write in the same language the user uses."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet.",
                    },
                    "profile_md": {
                        "type": "string",
                        "description": (
                            "The FULL markdown profile document. Include all previously known info "
                            "plus new info. Sections: basics, personality, health, daily routine."
                        ),
                    },
                },
                "required": ["pet_id", "profile_md"],
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
    {
        "type": "function",
        "function": {
            "name": "delete_pet",
            "description": (
                "Delete a pet profile. Use when the user wants to remove a pet "
                "from their account."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet to delete.",
                    },
                },
                "required": ["pet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event",
            "description": (
                "Delete a calendar event record. Use when the user wants to remove "
                "a previously logged event. You MUST first call query_calendar_events "
                "to find the event_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "UUID of the event to delete (from query_calendar_events results).",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": (
                "List the user's active reminders. Use when the user asks about "
                "their upcoming reminders or scheduled notifications."
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
            "name": "update_reminder",
            "description": (
                "Update an existing reminder. Use when the user wants to change "
                "the time, title, or details of a reminder. You MUST first call "
                "list_reminders to find the reminder_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {
                        "type": "string",
                        "description": "UUID of the reminder to update (from list_reminders results).",
                    },
                    "title": {
                        "type": "string",
                        "description": "New reminder title.",
                    },
                    "body": {
                        "type": "string",
                        "description": "New reminder body/description.",
                    },
                    "trigger_at": {
                        "type": "string",
                        "description": "New trigger time in ISO 8601 format (YYYY-MM-DDTHH:MM:SS).",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["medication", "vaccine", "checkup", "feeding", "grooming", "other"],
                        "description": "New reminder type.",
                    },
                },
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_reminder",
            "description": (
                "Delete/cancel a reminder. Use when the user wants to cancel a "
                "scheduled reminder. You MUST first call list_reminders to find "
                "the reminder_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {
                        "type": "string",
                        "description": "UUID of the reminder to delete (from list_reminders results).",
                    },
                },
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upload_event_photo",
            "description": (
                "Attach the user's photo to a calendar event. "
                "The photo is automatically taken from the user's attached image. "
                "Use when the user sends a photo and asks to add it to a specific event record."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "UUID of the event to attach the photo to.",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_language",
            "description": (
                "Change the app's display language. Use when the user asks to "
                "switch language."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "enum": ["zh", "en"],
                        "description": "Language code to switch to.",
                    },
                },
                "required": ["language"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_pet_avatar",
            "description": (
                "Set a pet's avatar/profile photo from the user's attached image. "
                "The photo is automatically taken from the user's message. "
                "Use when the user sends a photo and says to use it as a pet's avatar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet.",
                    },
                },
                "required": ["pet_id"],
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
    # Resolve pet(s): support both pet_id (single) and pet_ids (multi)
    raw_pet_ids = arguments.get("pet_ids") or []
    if not raw_pet_ids and arguments.get("pet_id"):
        raw_pet_ids = [arguments["pet_id"]]
    pet_ids_str = [str(pid) for pid in raw_pet_ids]

    event_date = date.fromisoformat(arguments["event_date"])
    title = arguments["title"]
    category = EventCategory(arguments["category"])
    event_time_str = arguments.get("event_time")
    raw_text = arguments.get("raw_text", "")

    event_time = None
    if event_time_str:
        parts = event_time_str.split(":")
        event_time = time(int(parts[0]), int(parts[1]))

    # Verify pets belong to user and collect names
    pet_names: list[str] = []
    first_pet_id = None
    if pet_ids_str:
        for pid_str in pet_ids_str:
            pid = uuid.UUID(pid_str)
            result = await db.execute(select(Pet).where(Pet.id == pid, Pet.user_id == user_id))
            pet = result.scalar_one_or_none()
            if pet:
                pet_names.append(pet.name)
                if first_pet_id is None:
                    first_pet_id = pid

    event = CalendarEvent(
        user_id=user_id,
        pet_id=first_pet_id,  # backward compat
        pet_ids=pet_ids_str,
        event_date=event_date,
        event_time=event_time,
        title=title,
        type=EventType.log,
        category=category,
        raw_text=raw_text,
        source=EventSource.chat,
        edited=False,
    )

    # Attach photos if provided
    photo_urls = arguments.get("photo_urls", [])
    if photo_urls:
        event.photos = photo_urls

    db.add(event)
    await db.flush()

    card = {
        "type": "record",
        "pet_name": ", ".join(pet_names) if pet_names else "",
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


async def _update_calendar_event(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Update an existing CalendarEvent."""
    event_id = uuid.UUID(arguments["event_id"])

    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id, CalendarEvent.user_id == user_id
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        return {"success": False, "error": "Event not found"}

    if "event_date" in arguments:
        event.event_date = date.fromisoformat(arguments["event_date"])
    if "event_time" in arguments:
        parts = arguments["event_time"].split(":")
        event.event_time = time(int(parts[0]), int(parts[1]))
    if "title" in arguments:
        event.title = arguments["title"]
    if "category" in arguments:
        event.category = EventCategory(arguments["category"])

    event.edited = True
    await db.flush()

    # Load pet name for card
    pet_result = await db.execute(select(Pet).where(Pet.id == event.pet_id))
    pet = pet_result.scalar_one_or_none()

    card = {
        "type": "record",
        "pet_name": pet.name if pet else "Unknown",
        "date": event.event_date.isoformat(),
        "category": event.category.value,
        "title": event.title,
    }

    return {
        "success": True,
        "event_id": str(event.id),
        "title": event.title,
        "event_date": event.event_date.isoformat(),
        "card": card,
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

    card = {
        "type": "pet_updated",
        "pet_name": pet.name,
        "saved_keys": list(info.keys()),
    }

    return {
        "success": True,
        "pet_id": str(pet.id),
        "pet_name": pet.name,
        "saved_keys": list(info.keys()),
        "card": card,
    }


async def _save_pet_profile_md(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Save the pet's narrative markdown profile."""
    pet_id = uuid.UUID(arguments["pet_id"])
    profile_md = arguments.get("profile_md", "").strip()
    if not profile_md:
        return {"success": False, "error": "Empty profile_md"}
    if len(profile_md) > 3000:
        return {"success": False, "error": "profile_md too long (max 3000 chars)"}

    result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        return {"success": False, "error": "Pet not found"}

    pet.profile_md = profile_md
    await db.flush()

    return {"success": True, "pet_id": str(pet.id), "pet_name": pet.name}


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


async def _delete_pet(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Delete a pet profile."""
    pet_id = uuid.UUID(arguments["pet_id"])

    result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        return {"success": False, "error": "Pet not found"}

    pet_name = pet.name
    await db.delete(pet)
    await db.flush()

    return {
        "success": True,
        "pet_id": str(pet_id),
        "pet_name": pet_name,
    }


async def _delete_calendar_event(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Delete a calendar event record."""
    event_id = uuid.UUID(arguments["event_id"])

    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id, CalendarEvent.user_id == user_id
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        return {"success": False, "error": "Event not found"}

    title = event.title
    await db.delete(event)
    await db.flush()

    return {
        "success": True,
        "event_id": str(event_id),
        "title": title,
    }


async def _list_reminders(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """List the user's active (unsent) reminders."""
    result = await db.execute(
        select(Reminder)
        .where(Reminder.user_id == user_id, Reminder.sent == False)  # noqa: E712
        .order_by(Reminder.trigger_at)
    )
    reminders = result.scalars().all()

    return {
        "reminders": [
            {
                "id": str(r.id),
                "pet_id": str(r.pet_id),
                "type": r.type,
                "title": r.title,
                "body": r.body,
                "trigger_at": r.trigger_at.isoformat() if r.trigger_at else None,
            }
            for r in reminders
        ],
        "count": len(reminders),
    }


async def _update_reminder(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Update an existing reminder."""
    reminder_id = uuid.UUID(arguments["reminder_id"])

    result = await db.execute(
        select(Reminder).where(
            Reminder.id == reminder_id, Reminder.user_id == user_id
        )
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        return {"success": False, "error": "Reminder not found"}

    if "title" in arguments:
        reminder.title = arguments["title"]
    if "body" in arguments:
        reminder.body = arguments["body"]
    if "trigger_at" in arguments:
        reminder.trigger_at = datetime.fromisoformat(arguments["trigger_at"])
    if "type" in arguments:
        reminder.type = arguments["type"]

    await db.flush()

    # Load pet name for card
    pet_result = await db.execute(select(Pet).where(Pet.id == reminder.pet_id))
    pet = pet_result.scalar_one_or_none()

    card = {
        "type": "reminder",
        "pet_name": pet.name if pet else "Unknown",
        "title": reminder.title,
        "trigger_at": reminder.trigger_at.isoformat() if reminder.trigger_at else None,
        "reminder_type": reminder.type,
    }

    return {
        "success": True,
        "reminder_id": str(reminder.id),
        "title": reminder.title,
        "trigger_at": reminder.trigger_at.isoformat() if reminder.trigger_at else None,
        "card": card,
    }


async def _delete_reminder(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Delete/cancel a reminder."""
    reminder_id = uuid.UUID(arguments["reminder_id"])

    result = await db.execute(
        select(Reminder).where(
            Reminder.id == reminder_id, Reminder.user_id == user_id
        )
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        return {"success": False, "error": "Reminder not found"}

    title = reminder.title
    await db.delete(reminder)
    await db.flush()

    return {
        "success": True,
        "reminder_id": str(reminder_id),
        "title": title,
    }


async def _upload_event_photo(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    images: list[str] | None = None,
    **_kwargs,
) -> dict:
    """Attach a photo to a calendar event."""
    event_id = uuid.UUID(arguments["event_id"])

    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id, CalendarEvent.user_id == user_id
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        return {"success": False, "error": "Event not found"}

    # Prefer image from user's attached photos, fall back to arguments
    img_b64 = (images[0] if images else None) or arguments.get("image_base64")
    if not img_b64:
        return {"success": False, "error": "No image provided. Ask the user to attach a photo."}
    image_data = base64.b64decode(img_b64)
    if len(image_data) > 5 * 1024 * 1024:
        return {"success": False, "error": "Image must be under 5MB"}

    photo_id = uuid.uuid4()
    filename = f"{photo_id}.jpg"
    filepath = PHOTO_DIR / filename
    filepath.write_bytes(image_data)

    photo_url = f"/api/v1/calendar/photos/{filename}"
    photos = list(event.photos) if event.photos else []
    photos.append(photo_url)
    event.photos = photos
    await db.flush()

    return {
        "success": True,
        "event_id": str(event_id),
        "photo_url": photo_url,
    }


async def _set_language(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Change the app display language (frontend-only action)."""
    language = arguments["language"]

    card = {
        "type": "set_language",
        "language": language,
    }

    return {
        "success": True,
        "language": language,
        "card": card,
    }


async def _set_pet_avatar(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    images: list[str] | None = None,
    **_kwargs,
) -> dict:
    """Set a pet's avatar from a base64 image."""
    pet_id = uuid.UUID(arguments["pet_id"])

    result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        return {"success": False, "error": "Pet not found"}

    # Prefer image from user's attached photos, fall back to arguments
    img_b64 = (images[0] if images else None) or arguments.get("image_base64")
    if not img_b64:
        return {"success": False, "error": "No image provided. Ask the user to attach a photo."}
    image_data = base64.b64decode(img_b64)
    if len(image_data) > 5 * 1024 * 1024:
        return {"success": False, "error": "Image must be under 5MB"}

    filename = f"{pet_id}.jpg"
    filepath = UPLOAD_DIR / filename
    filepath.write_bytes(image_data)

    pet.avatar_url = f"/api/v1/pets/{pet_id}/avatar"
    await db.flush()

    return {
        "success": True,
        "pet_id": str(pet_id),
        "pet_name": pet.name,
        "avatar_url": pet.avatar_url,
    }


_TOOL_HANDLERS = {
    "create_calendar_event": _create_calendar_event,
    "query_calendar_events": _query_calendar_events,
    "update_calendar_event": _update_calendar_event,
    "create_pet": _create_pet,
    "update_pet_profile": _update_pet_profile,
    "save_pet_profile_md": _save_pet_profile_md,
    "list_pets": _list_pets,
    "create_reminder": _create_reminder,
    "search_places": _search_places,
    "draft_email": _draft_email,
    "delete_pet": _delete_pet,
    "delete_calendar_event": _delete_calendar_event,
    "list_reminders": _list_reminders,
    "update_reminder": _update_reminder,
    "delete_reminder": _delete_reminder,
    "upload_event_photo": _upload_event_photo,
    "set_language": _set_language,
    "set_pet_avatar": _set_pet_avatar,
}

# Tools that accept extra kwargs (e.g., location, images)
_TOOLS_WITH_KWARGS = {"search_places", "upload_event_photo", "set_pet_avatar"}


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
