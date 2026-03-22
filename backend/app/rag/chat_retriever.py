"""Chat history retriever — searches chat turns and daily summaries."""

import logging
from uuid import UUID

from sqlalchemy import select

from app.database import async_session
from app.models import Embedding, SourceType
from app.rag.base import BaseRetriever, RetrievalResult

logger = logging.getLogger(__name__)


class ChatHistoryRetriever(BaseRetriever):
    async def retrieve(
        self,
        query_embedding: list[float],
        user_id: UUID,
        top_k: int = 10,
        pet_id: UUID | None = None,
    ) -> list[RetrievalResult]:
        try:
            async with async_session() as db:
                query = (
                    select(
                        Embedding.content,
                        Embedding.source_type,
                        Embedding.source_id,
                        Embedding.metadata_json,
                        Embedding.embedding.cosine_distance(query_embedding).label("_cosine_distance"),
                    )
                    .where(
                        Embedding.user_id == user_id,
                        Embedding.source_type.in_([SourceType.chat_turn, SourceType.daily_summary]),
                    )
                    .order_by("_cosine_distance")
                    .limit(top_k)
                )

                if pet_id is not None:
                    query = query.where(Embedding.pet_id == pet_id)

                result = await db.execute(query)
                rows = result.all()

                return [
                    RetrievalResult(
                        content=row.content,
                        source_type=row.source_type.value if hasattr(row.source_type, 'value') else row.source_type,
                        source_id=str(row.source_id),
                        score=1.0 - row._cosine_distance,
                        metadata=row.metadata_json or {},
                    )
                    for row in rows
                ]
        except Exception as exc:
            logger.warning("chat_retriever_error", extra={"error": str(exc)[:200]})
            return []
