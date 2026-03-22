"""Async embedding writers — fire-and-forget, never block the chat response."""

import logging
import uuid
from datetime import date

from app.database import async_session
from app.models import Embedding, SourceType
from app.rag.embedder import get_embedding_service

logger = logging.getLogger(__name__)


async def write_chat_turn(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    user_msg: str,
    assistant_msg: str,
    session_date: date,
    pet_id: uuid.UUID | None = None,
) -> None:
    """Embed and store a chat turn. Runs as background task."""
    try:
        content = f"User: {user_msg}\nAssistant: {assistant_msg}"
        embedding = await get_embedding_service().embed(content)
        if embedding is None:
            return

        record = Embedding(
            id=uuid.uuid4(),
            user_id=user_id,
            pet_id=pet_id,
            source_type=SourceType.chat_turn,
            source_id=session_id,
            content=content,
            embedding=embedding,
            metadata_json={"session_date": session_date.isoformat()},
        )
        async with async_session() as db:
            db.add(record)
            await db.commit()
        logger.info("embedding_written", extra={"source_type": "chat_turn"})
    except Exception as exc:
        logger.warning("embedding_write_error", extra={
            "source_type": "chat_turn", "error": str(exc)[:200],
        })


async def write_calendar_event(
    user_id: uuid.UUID,
    pet_id: uuid.UUID,
    event_id: uuid.UUID,
    event_date: date,
    category: str,
    title: str,
    raw_text: str = "",
) -> None:
    """Embed and store a calendar event. Runs as background task."""
    try:
        content = f"{event_date.isoformat()} [{category}] {title}"
        if raw_text:
            content += f" · {raw_text}"

        embedding = await get_embedding_service().embed(content)
        if embedding is None:
            return

        record = Embedding(
            id=uuid.uuid4(),
            user_id=user_id,
            pet_id=pet_id,
            source_type=SourceType.calendar_event,
            source_id=event_id,
            content=content,
            embedding=embedding,
            metadata_json={
                "event_date": event_date.isoformat(),
                "category": category,
            },
        )
        async with async_session() as db:
            db.add(record)
            await db.commit()
        logger.info("embedding_written", extra={"source_type": "calendar_event"})
    except Exception as exc:
        logger.warning("embedding_write_error", extra={
            "source_type": "calendar_event", "error": str(exc)[:200],
        })
