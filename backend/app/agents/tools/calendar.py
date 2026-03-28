"""Calendar event tool handlers."""

import base64
import uuid
from datetime import date, time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CalendarEvent, EventCategory, EventSource, EventType, Pet

PHOTO_DIR = Path("/app/uploads/photos") if Path("/app/uploads").exists() else Path(__file__).resolve().parent.parent.parent / "uploads" / "photos"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)


async def create_calendar_event(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    images: list[str] | None = None,
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

    # Attach photos: from arguments (LLM-provided URLs) or from user's chat images (base64)
    photo_urls = arguments.get("photo_urls", [])
    if not photo_urls and images:
        # Auto-save base64 images from chat to disk
        for img_b64 in images:
            try:
                image_data = base64.b64decode(img_b64)
                if len(image_data) > 5 * 1024 * 1024:
                    continue
                photo_id = uuid.uuid4()
                filename = f"{photo_id}.jpg"
                filepath = PHOTO_DIR / filename
                filepath.write_bytes(image_data)
                photo_urls.append(f"/api/v1/calendar/photos/{filename}")
            except Exception:
                continue
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
            }
            for e in events
        ],
        "count": len(events),
    }


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


async def upload_event_photo(
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
        "card": {
            "type": "record",
            "pet_name": "",
            "date": str(arguments.get("event_date", "")),
            "category": "daily",
        },
    }
