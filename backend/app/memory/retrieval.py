from __future__ import annotations

import math
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import settings
from app.memory.embeddings import embed_text
from app.memory.types import KnowledgeSnippet, MemorySnippet, RetrievedContext
from app.models import MemoryNode, MemoryNodeType

EmbedFn = Callable[[str], Awaitable[list[float]]]
SearchFn = Callable[..., Awaitable[dict[str, list[tuple[Any, float]]]]]

TOP_K = 3
SEARCH_CANDIDATES = 12


def _node_type_value(node_type: Any) -> str:
    return node_type.value if hasattr(node_type, "value") else str(node_type)


async def _search_nodes(
    *,
    db: AsyncSession,
    query_embedding: list[float],
    user_id: uuid.UUID,
    pet_id: uuid.UUID | None,
    species: str | None,
    include_knowledge: bool,
) -> dict[str, list[tuple[MemoryNode, float]]]:
    distance = MemoryNode.embedding.cosine_distance(query_embedding).label("distance")
    user_filters = [
        MemoryNode.user_id == user_id,
        MemoryNode.node_type.in_([MemoryNodeType.behavioral, MemoryNodeType.cognitive]),
    ]
    if pet_id:
        user_filters.append(or_(MemoryNode.pet_id == pet_id, MemoryNode.pet_id.is_(None)))

    user_stmt = (
        select(MemoryNode, distance)
        .where(and_(*user_filters))
        .order_by(distance)
        .limit(SEARCH_CANDIDATES)
    )
    if not include_knowledge:
        rows = (await db.execute(user_stmt)).all()
    else:
        knowledge_filters = [MemoryNode.node_type == MemoryNodeType.knowledge]
        if species:
            knowledge_filters.append(
                or_(
                    MemoryNode.metadata_json["species"].as_string() == species,
                    MemoryNode.metadata_json["species"].as_string() == "all",
                )
            )
        knowledge_stmt = (
            select(MemoryNode, distance)
            .where(and_(*knowledge_filters))
            .order_by(distance)
            .limit(TOP_K)
        )
        combined = union_all(user_stmt, knowledge_stmt).subquery()
        combined_node = aliased(MemoryNode, combined)
        stmt = select(combined_node, combined.c.distance).order_by(combined.c.distance)
        rows = (await db.execute(stmt)).all()

    user_rows: list[tuple[MemoryNode, float]] = []
    knowledge_rows: list[tuple[MemoryNode, float]] = []
    for node, distance_value in rows:
        row = (node, distance_value)
        if _node_type_value(node.node_type) == MemoryNodeType.knowledge.value:
            knowledge_rows.append(row)
        else:
            user_rows.append(row)

    return {"user": user_rows, "knowledge": knowledge_rows}


def _recency_weight(occurred_at: datetime | None, now: datetime) -> float:
    if occurred_at is None:
        return 0.0
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    days = max((now - occurred_at).days, 0)
    return math.exp(-settings.memory_recency_lambda * days)


def _user_score(node: Any, distance: float, now: datetime) -> float:
    if node.node_type == MemoryNodeType.behavioral:
        return distance - (settings.memory_recency_weight * _recency_weight(node.occurred_at, now))
    return distance


def _to_memory_snippet(node: Any, distance: float) -> MemorySnippet:
    meta = node.metadata_json or {}
    return MemorySnippet(
        kind=node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type),
        content=node.content,
        date=meta.get("date"),
        entity_id=str(node.source_id) if node.source_id else str(node.id),
        score=float(distance) if distance is not None else None,
        metadata=meta,
    )


def _to_knowledge_snippet(node: Any, distance: float) -> KnowledgeSnippet:
    meta = node.metadata_json or {}
    return KnowledgeSnippet(
        title=node.title or meta.get("title", ""),
        content=node.content,
        url=meta.get("url"),
        score=float(distance) if distance is not None else None,
        metadata=meta,
    )


async def retrieve_memweaver_context(
    *,
    query: str,
    db: AsyncSession,
    user_id: uuid.UUID,
    pet_id: uuid.UUID | None = None,
    species: str | None = None,
    include_knowledge: bool = True,
    embed: EmbedFn = embed_text,
    search_nodes: SearchFn = _search_nodes,
    now: datetime | None = None,
) -> RetrievedContext:
    now = now or datetime.now(UTC)
    query_embedding = await embed(query)
    rows = await search_nodes(
        db=db,
        query_embedding=query_embedding,
        user_id=user_id,
        pet_id=pet_id,
        species=species,
        include_knowledge=include_knowledge,
    )

    threshold = settings.memory_distance_threshold
    user_rows = [
        (node, float(distance))
        for node, distance in rows.get("user", [])
        if distance is not None and float(distance) <= threshold
    ]
    user_rows.sort(key=lambda item: _user_score(item[0], item[1], now))

    behavioral: list[MemorySnippet] = []
    cognitive: list[MemorySnippet] = []
    for node, distance in user_rows:
        if node.node_type == MemoryNodeType.cognitive:
            cognitive.append(_to_memory_snippet(node, distance))
        else:
            behavioral.append(_to_memory_snippet(node, distance))

    knowledge: list[KnowledgeSnippet] = []
    if include_knowledge:
        for node, distance in rows.get("knowledge", []):
            if distance is None or float(distance) > threshold:
                continue
            knowledge.append(_to_knowledge_snippet(node, float(distance)))

    return RetrievedContext(
        behavioral_memories=behavioral[:TOP_K],
        cognitive_memories=cognitive[:TOP_K],
        knowledge_snippets=knowledge[:TOP_K],
    )
