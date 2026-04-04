"""Reminder tool handlers."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Pet, Reminder
from app.agents.tools.registry import register_tool


@register_tool("create_reminder")
async def create_reminder(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Compatibility layer — redirects to create_calendar_event with reminder_at."""
    from app.agents.tools.calendar import create_calendar_event

    trigger_at = arguments.get("trigger_at", "")
    event_date = trigger_at[:10] if len(trigger_at) >= 10 else ""
    event_time = trigger_at[11:16] if len(trigger_at) >= 16 else None

    # Map reminder type to event category
    rtype = arguments.get("type", "other")
    category_map = {"vaccine": "medical", "checkup": "medical", "medication": "medical",
                    "feeding": "diet", "grooming": "daily"}
    category = category_map.get(rtype, "daily")

    cal_args = {
        "pet_id": arguments.get("pet_id"),
        "event_date": event_date,
        "title": arguments.get("title", ""),
        "category": category,
        "reminder_at": trigger_at,
    }
    if event_time:
        cal_args["event_time"] = event_time

    return await create_calendar_event(cal_args, db, user_id)


@register_tool("list_reminders")
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


@register_tool("update_reminder")
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


@register_tool("delete_all_reminders")
async def delete_all_reminders(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Delete all unsent reminders for the user."""
    result = await db.execute(
        select(Reminder)
        .where(Reminder.user_id == user_id, Reminder.sent == False)  # noqa: E712
    )
    reminders = result.scalars().all()

    if not reminders:
        return {"success": True, "deleted_count": 0, "message": "No reminders to delete"}

    count = len(reminders)
    for r in reminders:
        await db.delete(r)
    await db.flush()

    return {
        "success": True,
        "deleted_count": count,
    }


@register_tool("delete_reminder")
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
