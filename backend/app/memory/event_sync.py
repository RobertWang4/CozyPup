"""Keep MemWeaver behavioral memory in sync with calendar events."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, time

from sqlalchemy import select

from app.database import async_session
from app.memory.store import delete_memory_for_source, upsert_behavioral_memory
from app.models import CalendarEvent, MemoryNodeType

logger = logging.getLogger(__name__)


def _event_content(event: CalendarEvent) -> str:
    parts = [f"[{event.category.value}] {event.title}"]
    if event.raw_text:
        parts.append(event.raw_text)
    if event.notes:
        parts.append(f"notes: {event.notes}")
    parts.append(f"date: {event.event_date.isoformat()}")
    return "\n".join(parts)


def _event_metadata(event: CalendarEvent) -> dict:
    return {
        "date": event.event_date.isoformat(),
        "category": event.category.value if event.category else None,
        "title": event.title,
        "event_id": str(event.id),
        "pet_id": str(event.pet_id) if event.pet_id else None,
    }


def _event_occurred_at(event: CalendarEvent) -> datetime:
    return datetime.combine(event.event_date, time.min, tzinfo=UTC)


async def sync_event_memory(event_id: uuid.UUID) -> None:
    try:
        async with async_session() as db:
            result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
            event = result.scalar_one_or_none()
            if not event:
                return
            await upsert_behavioral_memory(
                db=db,
                user_id=event.user_id,
                pet_id=event.pet_id,
                source_kind="calendar_event",
                source_id=event.id,
                title=event.title,
                content=_event_content(event),
                metadata=_event_metadata(event),
                occurred_at=_event_occurred_at(event),
            )
    except Exception as exc:
        logger.warning("event_memory_sync_error", extra={
            "event_id": str(event_id),
            "error": str(exc)[:200],
        })


async def delete_event_memory(event_id: uuid.UUID) -> None:
    try:
        async with async_session() as db:
            await delete_memory_for_source(
                db=db,
                source_kind="calendar_event",
                source_id=event_id,
                node_type=MemoryNodeType.behavioral,
            )
    except Exception as exc:
        logger.warning("event_memory_delete_error", extra={
            "event_id": str(event_id),
            "error": str(exc)[:200],
        })


def schedule_event_memory(event_id: uuid.UUID | str) -> None:
    if isinstance(event_id, str):
        try:
            event_id = uuid.UUID(event_id)
        except ValueError:
            return
    asyncio.create_task(sync_event_memory(event_id))


def schedule_event_memory_delete(event_id: uuid.UUID | str) -> None:
    if isinstance(event_id, str):
        try:
            event_id = uuid.UUID(event_id)
        except ValueError:
            return
    asyncio.create_task(delete_event_memory(event_id))
