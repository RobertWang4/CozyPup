"""Calendar event retriever — searches events with 7-day context expansion."""

import logging
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select

from app.database import async_session
from app.models import CalendarEvent, Embedding, SourceType
from app.rag.base import BaseRetriever, RetrievalResult

logger = logging.getLogger(__name__)


class CalendarRetriever(BaseRetriever):
    async def retrieve(
        self,
        query_embedding: list[float],
        user_id: UUID,
        top_k: int = 10,
        pet_id: UUID | None = None,
    ) -> list[RetrievalResult]:
        try:
            async with async_session() as db:
                # Vector search for matching events
                query = (
                    select(
                        Embedding.content,
                        Embedding.source_type,
                        Embedding.source_id,
                        Embedding.pet_id,
                        Embedding.metadata_json,
                        Embedding.embedding.cosine_distance(query_embedding).label("_cosine_distance"),
                    )
                    .where(
                        Embedding.user_id == user_id,
                        Embedding.source_type == SourceType.calendar_event,
                    )
                    .order_by("_cosine_distance")
                    .limit(top_k)
                )

                if pet_id is not None:
                    query = query.where(Embedding.pet_id == pet_id)

                result = await db.execute(query)
                rows = result.all()

                results = [
                    RetrievalResult(
                        content=row.content,
                        source_type="calendar_event",
                        source_id=str(row.source_id),
                        score=1.0 - row._cosine_distance,
                        metadata={
                            **(row.metadata_json or {}),
                            "pet_id": str(row.pet_id) if row.pet_id else None,
                        },
                    )
                    for row in rows
                ]

                # Context expansion: for each hit, pull same-pet same-category events from past 7 days
                expanded = await self._expand_context(db, user_id, results)
                return expanded

        except Exception as exc:
            logger.warning("calendar_retriever_error", extra={"error": str(exc)[:200]})
            return []

    async def _expand_context(
        self, db, user_id: UUID, results: list[RetrievalResult]
    ) -> list[RetrievalResult]:
        """Pull related events from the past 7 days for context."""
        if not results:
            return results

        seen_ids = {r.source_id for r in results}
        expanded = list(results)
        today = date.today()
        week_ago = today - timedelta(days=7)

        # Collect unique (pet_id, category) pairs from hits
        # pet_id comes from the Embedding.pet_id column (stored in metadata by retriever)
        pairs = set()
        for r in results:
            cat = r.metadata.get("category")
            pet = r.metadata.get("pet_id")
            if cat and pet:
                pairs.add((pet, cat))

        if not pairs:
            return results

        # Query calendar_events directly for expansion (not via embeddings)
        for pet_id_str, category in pairs:
            try:
                pet_uuid = UUID(pet_id_str) if isinstance(pet_id_str, str) else pet_id_str
                query = (
                    select(CalendarEvent)
                    .where(
                        CalendarEvent.user_id == user_id,
                        CalendarEvent.pet_id == pet_uuid,
                        CalendarEvent.category == category,
                        CalendarEvent.event_date >= week_ago,
                        CalendarEvent.event_date <= today,
                    )
                    .order_by(CalendarEvent.event_date.desc())
                    .limit(10)
                )
                result = await db.execute(query)
                events = result.scalars().all()

                for evt in events:
                    if str(evt.id) not in seen_ids:
                        seen_ids.add(str(evt.id))
                        content = f"{evt.event_date.isoformat()} [{evt.category.value}] {evt.title}"
                        expanded.append(RetrievalResult(
                            content=content,
                            source_type="calendar_event",
                            source_id=str(evt.id),
                            score=0.5,  # Lower score for expansion results
                            metadata={
                                "event_date": evt.event_date.isoformat(),
                                "category": evt.category.value,
                                "expanded": True,
                            },
                        ))
            except Exception:
                continue

        return expanded
