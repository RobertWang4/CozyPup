"""Backfill calendar_event embeddings for rows that don't have one.

Usage:
    python -m app.rag.backfill_events                 # all users
    python -m app.rag.backfill_events --user EMAIL    # single user
    python -m app.rag.backfill_events --dry-run
"""

import argparse
import asyncio
import logging

from sqlalchemy import select

from app.database import async_session
from app.models import CalendarEvent, Embedding, SourceType, User
from app.rag.event_sync import sync_event_embedding

logger = logging.getLogger(__name__)


async def _events_needing_embedding(user_email: str | None) -> list:
    async with async_session() as db:
        stmt = select(CalendarEvent.id, CalendarEvent.user_id)
        if user_email:
            user = (await db.execute(
                select(User).where(User.email == user_email)
            )).scalar_one_or_none()
            if not user:
                print(f"User not found: {user_email}")
                return []
            stmt = stmt.where(CalendarEvent.user_id == user.id)

        existing = select(Embedding.source_id).where(
            Embedding.source_type == SourceType.calendar_event
        )
        stmt = stmt.where(CalendarEvent.id.notin_(existing))

        rows = (await db.execute(stmt)).all()
        return [r.id for r in rows]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill event embeddings")
    parser.add_argument("--user", help="Only backfill events for this user email")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    event_ids = await _events_needing_embedding(args.user)
    print(f"Found {len(event_ids)} events without embeddings")

    if args.dry_run or not event_ids:
        return

    for i, event_id in enumerate(event_ids, 1):
        await sync_event_embedding(event_id)
        if i % 10 == 0:
            print(f"  {i}/{len(event_ids)}")
    print(f"Done: {len(event_ids)} events embedded")


if __name__ == "__main__":
    asyncio.run(main())
