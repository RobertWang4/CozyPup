"""Calendar event tool handlers — create/query/update/delete + photos + location.

CalendarEvent replaces the old pet_logs table; category/raw_text/edited/
source fields encode whether the record came from chat, manual entry, or
an edit. `create_calendar_event` is the workhorse — it handles multi-pet
events via `pet_ids` and auto-dedups abnormal events on (pet, title, date)
to absorb the LLM's occasional duplicate-call failure mode.
"""

import uuid
from datetime import date, time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models import CalendarEvent, EventCategory, EventSource, EventType, Pet
from app.agents.tools.registry import register_tool


@register_tool("create_calendar_event", accepts_kwargs=True)
async def create_calendar_event(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    **kwargs,
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

    if pet_ids_str and not pet_names:
        return {"success": False, "error": "No valid pets found for the given pet_id(s)"}

    cost = arguments.get("cost")
    notes = arguments.get("notes")
    reminder_at_str = arguments.get("reminder_at")
    reminder_at = None
    if reminder_at_str:
        from datetime import datetime as _dt
        try:
            reminder_at = _dt.fromisoformat(reminder_at_str)
        except ValueError:
            pass

    # Idempotency: abnormal events with same (pet, title, date) are treated as
    # duplicates. Defensive re-creation by LLM is a known failure mode —
    # return success with already_exists=True and emit no card.
    if category == EventCategory.abnormal and first_pet_id:
        dup_q = select(CalendarEvent).where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.pet_id == first_pet_id,
            CalendarEvent.title == title,
            CalendarEvent.event_date == event_date,
            CalendarEvent.category == EventCategory.abnormal,
        )
        existing = (await db.execute(dup_q)).scalar_one_or_none()
        if existing:
            return {
                "success": True,
                "already_exists": True,
                "event_id": str(existing.id),
                "title": existing.title,
                "category": existing.category.value,
                "event_date": existing.event_date.isoformat(),
                "message": f"'{title}' 已记录过，未重复创建",
            }

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
        cost=float(cost) if cost is not None else None,
        reminder_at=reminder_at,
        notes=notes if notes else None,
    )

    # Photo attachment: chat.py already persisted the files, so we just
    # get back a list of URL paths via kwargs["image_urls"].
    # Fallback to arguments["_image_urls"] — populated when the call was
    # deferred through a confirm card (see orchestrator.dispatch_tool).
    image_urls = (
        kwargs.get("image_urls")
        or arguments.get("_image_urls")
        or []
    )
    if image_urls:
        event.photos = image_urls

    db.add(event)
    await db.flush()

    card = {
        "type": "record",
        "pet_name": ", ".join(pet_names) if pet_names else "",
        "date": arguments["event_date"],
        "category": arguments["category"],
        "title": title,
        "cost": float(cost) if cost is not None else None,
        "reminder_at": reminder_at_str,
        "photos_count": len(image_urls) if image_urls else 0,
        "event_time": event_time_str,
        "raw_text": raw_text or None,
    }

    return {
        "success": True,
        "event_id": str(event.id),
        "title": title,
        "category": arguments["category"],
        "event_date": arguments["event_date"],
        "card": card,
    }


@register_tool("query_calendar_events")
async def query_calendar_events(
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
                "cost": e.cost,
            }
            for e in events
        ],
        "count": len(events),
    }


@register_tool("update_calendar_event")
async def update_calendar_event(
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

    old_date = event.event_date.isoformat()
    if "event_date" in arguments:
        event.event_date = date.fromisoformat(arguments["event_date"])
    if "event_time" in arguments:
        parts = arguments["event_time"].split(":")
        event.event_time = time(int(parts[0]), int(parts[1]))
    if "title" in arguments:
        event.title = arguments["title"]
    if "category" in arguments:
        event.category = EventCategory(arguments["category"])
    if "cost" in arguments:
        event.cost = float(arguments["cost"]) if arguments["cost"] is not None else None
    if "notes" in arguments:
        n = arguments.get("notes")
        event.notes = n if n else None

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
        "old_date": old_date,
    }

    return {
        "success": True,
        "event_id": str(event.id),
        "title": event.title,
        "event_date": event.event_date.isoformat(),
        "card": card,
    }


@register_tool("delete_calendar_event")
async def delete_calendar_event(
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
        "card": {
            "type": "event_deleted",
            "title": title,
        },
    }


@register_tool("upload_event_photo", accepts_kwargs=True)
async def upload_event_photo(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    **kwargs,
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

    # chat.py has already saved the files — just get the URL list via kwargs.
    image_urls = kwargs.get("image_urls") or []

    if not image_urls:
        return {"success": False, "error": "No image provided. Ask the user to attach a photo."}

    photos = list(event.photos) if event.photos else []
    added = [url for url in image_urls if url not in photos]
    if not added:
        return {"success": True, "message": f"Photos already attached to '{event.title}'."}
    photos.extend(added)
    event.photos = photos
    flag_modified(event, "photos")
    await db.flush()

    return {
        "success": True,
        "message": f"Added {len(added)} photo(s) to event '{event.title}'.",
    }


@register_tool("remove_event_photo")
async def remove_event_photo(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Remove a specific photo from a calendar event."""
    event_id = uuid.UUID(arguments["event_id"])
    photo_index = arguments.get("photo_index", 0)

    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id, CalendarEvent.user_id == user_id
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        return {"success": False, "error": "Event not found"}

    photos = list(event.photos) if event.photos else []
    if not photos:
        return {"success": False, "error": "Event has no photos."}

    if photo_index < 0 or photo_index >= len(photos):
        return {"success": False, "error": f"Invalid photo_index {photo_index}. Event has {len(photos)} photo(s) (0-indexed)."}

    removed = photos.pop(photo_index)
    event.photos = photos
    flag_modified(event, "photos")
    await db.flush()

    # Get pet name for card
    pet_name = ""
    if event.pet_id:
        pet_result = await db.execute(select(Pet).where(Pet.id == event.pet_id))
        pet = pet_result.scalar_one_or_none()
        if pet:
            pet_name = pet.name

    return {
        "success": True,
        "remaining_count": len(photos),
        "message": f"Removed photo {photo_index + 1} from '{event.title}'. {len(photos)} photo(s) remaining.",
        "card": {
            "type": "record",
            "pet_name": pet_name,
            "date": str(event.event_date),
            "category": event.category.value if event.category else "daily",
            "title": event.title,
        },
    }


@register_tool("add_event_location")
async def add_event_location(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Add location to a calendar event."""
    event_id = uuid.UUID(arguments["event_id"])

    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id, CalendarEvent.user_id == user_id
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        return {"success": False, "error": "Event not found"}

    place_id = arguments.get("place_id", "")

    # Always fetch place details from Google API when place_id is available.
    # LLM-provided lat/lng is unreliable (often passes user's GPS instead of place coords).
    if place_id:
        from app.services.places import places_service
        details = await places_service.get_place_details(place_id)
        if details:
            event.location_name = details.get("name") or arguments.get("location_name", "")
            event.location_address = details.get("address") or arguments.get("location_address", "")
            event.location_lat = details.get("lat")
            event.location_lng = details.get("lng")
        else:
            # API failed, fall back to LLM values
            event.location_name = arguments.get("location_name", "")
            event.location_address = arguments.get("location_address", "")
            event.location_lat = arguments.get("lat")
            event.location_lng = arguments.get("lng")
    else:
        event.location_name = arguments.get("location_name", "")
        event.location_address = arguments.get("location_address", "")
        event.location_lat = arguments.get("lat")
        event.location_lng = arguments.get("lng")

    event.place_id = place_id
    await db.flush()

    return {
        "success": True,
        "event_id": str(event_id),
        "location_name": event.location_name,
        "card": {
            "type": "record",
            "pet_name": "",
            "date": event.event_date.isoformat(),
            "category": event.category.value,
            "title": event.title,
        },
    }
