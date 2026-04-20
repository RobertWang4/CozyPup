"""Vector similarity retrieval for knowledge base and user history."""

import logging
import uuid

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Embedding, SourceType
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

    Results whose cosine distance exceeds `settings.rag_distance_threshold`
    are dropped — irrelevant context hurts the LLM more than it helps.

    Returns:
        {
            "knowledge": [{"title": ..., "content": ..., "url": ..., "distance": ...}],
            "history":   [{"date": ..., "content": ..., "event_id": ..., "distance": ...}],
        }
    """
    query_embedding = await embed_text(query)
    threshold = settings.rag_distance_threshold

    distance = Embedding.embedding.cosine_distance(query_embedding).label("distance")

    # 1. Global knowledge base
    kb_filters = [Embedding.source_type == SourceType.knowledge_base]
    if species:
        kb_filters.append(
            or_(
                Embedding.metadata_json["species"].as_string() == species,
                Embedding.metadata_json["species"].as_string() == "all",
            )
        )
    kb_query = (
        select(Embedding, distance)
        .where(and_(*kb_filters))
        .order_by(distance)
        .limit(TOP_K)
    )
    kb_rows = (await db.execute(kb_query)).all()

    # 2. User history
    history_filters = [
        Embedding.user_id == user_id,
        Embedding.source_type.in_([SourceType.calendar_event, SourceType.daily_summary]),
    ]
    if pet_id:
        history_filters.append(Embedding.pet_id == pet_id)
    history_query = (
        select(Embedding, distance)
        .where(and_(*history_filters))
        .order_by(distance)
        .limit(TOP_K)
    )
    history_rows = (await db.execute(history_query)).all()

    # 3. Format + threshold filter
    knowledge = []
    for emb, dist in kb_rows:
        if dist is not None and dist > threshold:
            continue
        meta = emb.metadata_json or {}
        knowledge.append({
            "title": meta.get("title", ""),
            "content": emb.content,
            "url": meta.get("url"),
            "distance": float(dist) if dist is not None else None,
        })

    history = []
    for emb, dist in history_rows:
        if dist is not None and dist > threshold:
            continue
        meta = emb.metadata_json or {}
        history.append({
            "date": meta.get("date", ""),
            "content": emb.content,
            "event_id": meta.get("event_id"),
            "distance": float(dist) if dist is not None else None,
        })

    logger.info("rag_retrieve", extra={
        "query_len": len(query),
        "kb_candidates": len(kb_rows),
        "kb_kept": len(knowledge),
        "history_candidates": len(history_rows),
        "history_kept": len(history),
        "kb_top_distance": float(kb_rows[0][1]) if kb_rows else None,
        "history_top_distance": float(history_rows[0][1]) if history_rows else None,
        "threshold": threshold,
    })

    return {"knowledge": knowledge, "history": history}
