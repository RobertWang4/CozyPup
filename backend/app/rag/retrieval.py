"""Vector similarity retrieval for knowledge base and user history."""

import logging
import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Embedding, SourceType
from app.rag.embeddings import embed_texts
from app.rag.intent_filter import IntentHint, detect_intent
from app.rag.query_expansion import expand_query

logger = logging.getLogger(__name__)

TOP_K = 3


async def _search_kb(
    db: AsyncSession,
    query_embedding: list[float],
    species: str | None,
    title_patterns: list[str] | None = None,
) -> list[tuple]:
    """One vector search against the knowledge_base embeddings.

    If `title_patterns` is provided, results are restricted to embeddings
    whose metadata title case-insensitively contains any of those substrings.
    """
    distance = Embedding.embedding.cosine_distance(query_embedding).label("distance")
    filters = [Embedding.source_type == SourceType.knowledge_base]
    if species:
        filters.append(
            or_(
                Embedding.metadata_json["species"].as_string() == species,
                Embedding.metadata_json["species"].as_string() == "all",
            )
        )
    if title_patterns:
        title_col = Embedding.metadata_json["title"].as_string()
        filters.append(or_(*[title_col.ilike(f"%{p}%") for p in title_patterns]))

    stmt = (
        select(Embedding, distance)
        .where(and_(*filters))
        .order_by(distance)
        .limit(TOP_K)
    )
    return (await db.execute(stmt)).all()


async def _search_history(
    db: AsyncSession,
    query_embedding: list[float],
    user_id: uuid.UUID,
    pet_id: uuid.UUID | None,
) -> list[tuple]:
    distance = Embedding.embedding.cosine_distance(query_embedding).label("distance")
    filters = [
        Embedding.user_id == user_id,
        Embedding.source_type.in_([SourceType.calendar_event, SourceType.daily_summary]),
    ]
    if pet_id:
        filters.append(Embedding.pet_id == pet_id)

    stmt = (
        select(Embedding, distance)
        .where(and_(*filters))
        .order_by(distance)
        .limit(TOP_K)
    )
    return (await db.execute(stmt)).all()


def _merge_by_source(rows_lists: list[list[tuple]]) -> list[tuple]:
    """Union multiple result lists, keeping each source_id with its min distance."""
    best: dict[uuid.UUID, tuple] = {}
    for rows in rows_lists:
        for emb, dist in rows:
            if dist is None:
                continue
            prev = best.get(emb.source_id)
            if prev is None or dist < prev[1]:
                best[emb.source_id] = (emb, float(dist))
    return sorted(best.values(), key=lambda r: r[1])


async def retrieve_knowledge(
    query: str,
    db: AsyncSession,
    user_id: uuid.UUID,
    pet_id: uuid.UUID | None = None,
    species: str | None = None,
) -> dict:
    """Retrieve relevant knowledge + user history via vector similarity.

    Pipeline:
      1. Expand the query into 1-3 variants (LLM, best-effort, cached).
      2. Detect high-confidence intent ("dog ate chocolate" → boost toxic-food
         titles) via regex. If detected, run an extra title-constrained
         vector search alongside the main one.
      3. For each variant, run the main KB search and (if any) the intent
         boost search. Union by source_id, keeping the minimum distance.
      4. Apply `settings.rag_distance_threshold` to the merged result.
      5. Same query embedding is reused for the user history search.

    Returns:
        {
            "knowledge": [{"title", "content", "url", "distance"}],
            "history":   [{"date", "content", "event_id", "distance"}],
        }
    """
    threshold = settings.rag_distance_threshold

    variants = await expand_query(query)
    intent: IntentHint | None = (
        detect_intent(query) if settings.rag_enable_intent_filter else None
    )

    # Embed every variant in one batched call — embed_texts dedupes + caches.
    variant_vectors = await embed_texts(variants)

    # SQLAlchemy AsyncSession isn't safe for concurrent use — run searches
    # sequentially. Each query is < 20ms; total stays well under 200ms.
    kb_row_lists: list[list[tuple]] = []
    for vec in variant_vectors:
        kb_row_lists.append(await _search_kb(db, vec, species, None))

    if intent and intent.boost_title_patterns:
        for vec in variant_vectors:
            kb_row_lists.append(
                await _search_kb(db, vec, species, intent.boost_title_patterns)
            )

    # History search uses only the primary query — history is per-user and
    # usually short phrases, so variants rarely help.
    history_rows = await _search_history(db, variant_vectors[0], user_id, pet_id)

    kb_merged = _merge_by_source(kb_row_lists)[:TOP_K]
    kb_candidates_total = sum(len(r) for r in kb_row_lists)

    knowledge = []
    for emb, dist in kb_merged:
        if dist > threshold:
            continue
        meta = emb.metadata_json or {}
        knowledge.append({
            "title": meta.get("title", ""),
            "content": emb.content,
            "url": meta.get("url"),
            "distance": dist,
        })

    history = []
    for emb, dist in history_rows:
        dval = float(dist) if dist is not None else None
        if dval is not None and dval > threshold:
            continue
        meta = emb.metadata_json or {}
        history.append({
            "date": meta.get("date", ""),
            "content": emb.content,
            "event_id": meta.get("event_id"),
            "distance": dval,
        })

    logger.info("rag_retrieve", extra={
        "query_len": len(query),
        "variants": len(variants),
        "intent": intent.label if intent else None,
        "kb_candidates": kb_candidates_total,
        "kb_kept": len(knowledge),
        "history_candidates": len(history_rows),
        "history_kept": len(history),
        "kb_top_distance": knowledge[0]["distance"] if knowledge else None,
        "history_top_distance": history[0]["distance"] if history else None,
        "threshold": threshold,
    })

    return {"knowledge": knowledge, "history": history}
