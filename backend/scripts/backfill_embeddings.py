"""One-time script to backfill embeddings for existing calendar events and recent chat history."""

import asyncio
import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app.database import async_session
from app.models import CalendarEvent, Chat, ChatSession, Embedding, SourceType
from app.rag.embedder import get_embedding_service


async def backfill_calendar_events():
    """Embed all existing calendar events that don't have embeddings yet."""
    service = get_embedding_service()
    async with async_session() as db:
        # Find events without embeddings
        existing = select(Embedding.source_id).where(
            Embedding.source_type == SourceType.calendar_event
        )
        result = await db.execute(
            select(CalendarEvent).where(CalendarEvent.id.not_in(existing))
        )
        events = result.scalars().all()
        print(f"Found {len(events)} calendar events to backfill")

        for i, evt in enumerate(events):
            content = f"{evt.event_date.isoformat()} [{evt.category.value}] {evt.title}"
            if evt.raw_text:
                content += f" · {evt.raw_text}"

            embedding = await service.embed(content)
            if embedding is None:
                print(f"  [{i+1}] SKIP (embedding failed): {evt.title}")
                continue

            record = Embedding(
                id=uuid.uuid4(),
                user_id=evt.user_id,
                pet_id=evt.pet_id,
                source_type=SourceType.calendar_event,
                source_id=evt.id,
                content=content,
                embedding=embedding,
                metadata_json={
                    "event_date": evt.event_date.isoformat(),
                    "category": evt.category.value,
                },
            )
            db.add(record)
            print(f"  [{i+1}] OK: {evt.title}")

        await db.commit()
        print("Calendar backfill complete.")


async def backfill_chat_history(days: int = 30):
    """Embed recent chat turns (last N days)."""
    service = get_embedding_service()
    cutoff = date.today() - timedelta(days=days)

    async with async_session() as db:
        # Find sessions that don't already have chat_turn embeddings
        already_embedded = select(Embedding.source_id).where(
            Embedding.source_type == SourceType.chat_turn
        )
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.session_date >= cutoff,
                ChatSession.id.not_in(already_embedded),
            )
        )
        sessions = result.scalars().all()
        print(f"Found {len(sessions)} sessions in last {days} days")

        for session in sessions:
            result = await db.execute(
                select(Chat)
                .where(Chat.session_id == session.id)
                .order_by(Chat.created_at)
            )
            messages = result.scalars().all()

            # Pair user + assistant messages
            pairs = []
            for j in range(len(messages) - 1):
                if messages[j].role.value == "user" and messages[j+1].role.value == "assistant":
                    pairs.append((messages[j], messages[j+1]))

            for user_msg, asst_msg in pairs:
                content = f"User: {user_msg.content}\nAssistant: {asst_msg.content}"
                embedding = await service.embed(content)
                if embedding is None:
                    continue

                record = Embedding(
                    id=uuid.uuid4(),
                    user_id=session.user_id,
                    source_type=SourceType.chat_turn,
                    source_id=session.id,
                    content=content,
                    embedding=embedding,
                    metadata_json={"session_date": session.session_date.isoformat()},
                )
                db.add(record)

            print(f"  Session {session.session_date}: {len(pairs)} turns embedded")

        await db.commit()
        print("Chat history backfill complete.")


async def main():
    print("=== Backfilling calendar events ===")
    await backfill_calendar_events()
    print()
    print("=== Backfilling chat history (30 days) ===")
    await backfill_chat_history(30)


if __name__ == "__main__":
    asyncio.run(main())
