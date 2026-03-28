"""Reminder tool handlers."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Pet, Reminder


async def create_reminder(
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


async def list_reminders(
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


async def update_reminder(
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


async def delete_reminder(
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
        "card": {
            "type": "reminder_deleted",
            "title": title,
        },
    }
