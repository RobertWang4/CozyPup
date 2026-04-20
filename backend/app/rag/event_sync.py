"""Keep RAG embeddings in sync with calendar_events.

Used by:
- Agent tool handlers (create/update/delete_calendar_event) via orchestrator hook
- REST router endpoints (create/update/delete)
- Backfill script

All entry points are fire-and-forget background tasks — failures log but never
block the request. Source-of-truth is the `calendar_events` row; embeddings
are derived data and can be regenerated any time via `app.rag.backfill_events`.
"""

import asyncio
import logging
import uuid

from sqlalchemy import delete, select

from app.database import async_session
from app.models import CalendarEvent, Embedding, SourceType
from app.rag.embeddings import embed_text

logger = logging.getLogger(__name__)


def _event_content(event: CalendarEvent) -> str:
    """Build the text we embed for an event. Keep short — ~1 chunk only."""
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


async def sync_event_embedding(event_id: uuid.UUID) -> None:
    """Upsert the embedding for an event. Opens its own DB session."""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(CalendarEvent).where(CalendarEvent.id == event_id)
            )
            event = result.scalar_one_or_none()
            if not event:
                return

            content = _event_content(event)
            vector = await embed_text(content)

            # Upsert: delete any prior embedding for this event, then insert.
            await db.execute(
                delete(Embedding).where(
                    Embedding.source_type == SourceType.calendar_event,
                    Embedding.source_id == event_id,
                )
            )
            db.add(Embedding(
                user_id=event.user_id,
                pet_id=event.pet_id,
                source_type=SourceType.calendar_event,
                source_id=event.id,
                content=content,
                embedding=vector,
                metadata_json=_event_metadata(event),
            ))
            await db.commit()
    except Exception as exc:
        logger.warning("event_embedding_sync_error", extra={
            "event_id": str(event_id), "error": str(exc)[:200],
        })


async def delete_event_embedding(event_id: uuid.UUID) -> None:
    """Remove any embedding for an event. Opens its own DB session."""
    try:
        async with async_session() as db:
            await db.execute(
                delete(Embedding).where(
                    Embedding.source_type == SourceType.calendar_event,
                    Embedding.source_id == event_id,
                )
            )
            await db.commit()
    except Exception as exc:
        logger.warning("event_embedding_delete_error", extra={
            "event_id": str(event_id), "error": str(exc)[:200],
        })


def schedule_event_embedding(event_id: uuid.UUID | str) -> None:
    """Fire-and-forget background embedding sync."""
    if isinstance(event_id, str):
        try:
            event_id = uuid.UUID(event_id)
        except ValueError:
            return
    asyncio.create_task(sync_event_embedding(event_id))


def schedule_event_embedding_delete(event_id: uuid.UUID | str) -> None:
    """Fire-and-forget background embedding delete."""
    if isinstance(event_id, str):
        try:
            event_id = uuid.UUID(event_id)
        except ValueError:
            return
    asyncio.create_task(delete_event_embedding(event_id))
