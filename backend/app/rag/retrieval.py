"""Vector similarity retrieval for knowledge base and user history."""

import logging
import uuid

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Embedding, SourceType, KnowledgeArticle
from app.rag.embeddings import embed_text

logger = logging.getLogger(__name__)

TOP_K = 3


async def retrieve_knowledge(
    query: str,
    db: AsyncSession,
    user_id: uuid.UUID,
    pet_id: uuid.UUID | None = None,
    species: str | None = None,
) -> dict:
    """Retrieve relevant knowledge + user history via vector similarity.

    Returns:
        {
            "knowledge": [{"title": ..., "content": ..., "url": ...}],
            "history": [{"date": ..., "content": ..., "event_id": ...}],
        }
    """
    query_embedding = await embed_text(query)

    # 1. Search global knowledge base
    kb_filters = [Embedding.source_type == SourceType.knowledge_base]
    if species:
        kb_filters.append(
            or_(
                Embedding.metadata_json["species"].as_string() == species,
                Embedding.metadata_json["species"].as_string() == "all",
            )
        )

    kb_query = (
        select(Embedding)
        .where(and_(*kb_filters))
        .order_by(Embedding.embedding.cosine_distance(query_embedding))
        .limit(TOP_K)
    )
    kb_result = await db.execute(kb_query)
    kb_rows = kb_result.scalars().all()

    # 2. Search user history
    history_filters = [
        Embedding.user_id == user_id,
        Embedding.source_type.in_([SourceType.calendar_event, SourceType.daily_summary]),
    ]
    if pet_id:
        history_filters.append(Embedding.pet_id == pet_id)

    history_query = (
        select(Embedding)
        .where(and_(*history_filters))
        .order_by(Embedding.embedding.cosine_distance(query_embedding))
        .limit(TOP_K)
    )
    history_result = await db.execute(history_query)
    history_rows = history_result.scalars().all()

    # 3. Format results
    knowledge = []
    for row in kb_rows:
        meta = row.metadata_json or {}
        knowledge.append({
            "title": meta.get("title", ""),
            "content": row.content,
            "url": meta.get("url"),
        })

    history = []
    for row in history_rows:
        meta = row.metadata_json or {}
        history.append({
            "date": meta.get("date", ""),
            "content": row.content,
            "event_id": meta.get("event_id"),
        })

    return {"knowledge": knowledge, "history": history}
