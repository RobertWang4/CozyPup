from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Awaitable, Callable

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.embeddings import embed_text
from app.models import MemoryEdge, MemoryNode, MemoryNodeType

logger = logging.getLogger(__name__)

EmbedFn = Callable[[str], Awaitable[list[float]]]


async def _upsert_node(
    *,
    db: AsyncSession,
    node_type: MemoryNodeType,
    source_kind: str,
    source_id: uuid.UUID,
    content: str,
    embedding: list[float],
    title: str = "",
    user_id: uuid.UUID | None = None,
    pet_id: uuid.UUID | None = None,
    metadata: dict | None = None,
    occurred_at: datetime | None = None,
) -> MemoryNode:
    result = await db.execute(
        select(MemoryNode).where(
            MemoryNode.node_type == node_type,
            MemoryNode.source_kind == source_kind,
            MemoryNode.source_id == source_id,
        )
    )
    node = result.scalar_one_or_none()
    if node is None:
        node = MemoryNode(
            id=uuid.uuid4(),
            node_type=node_type,
            source_kind=source_kind,
            source_id=source_id,
            user_id=user_id,
            pet_id=pet_id,
            title=title,
            content=content,
            embedding=embedding,
            metadata_json=metadata,
            occurred_at=occurred_at,
        )
        db.add(node)
    else:
        node.user_id = user_id
        node.pet_id = pet_id
        node.title = title
        node.content = content
        node.embedding = embedding
        node.metadata_json = metadata
        node.occurred_at = occurred_at
    await db.commit()
    return node


async def upsert_behavioral_memory(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    source_kind: str,
    source_id: uuid.UUID,
    content: str,
    pet_id: uuid.UUID | None = None,
    title: str = "",
    metadata: dict | None = None,
    occurred_at: datetime | None = None,
    embed: EmbedFn = embed_text,
) -> MemoryNode | None:
    try:
        vector = await embed(content)
        return await _upsert_node(
            db=db,
            node_type=MemoryNodeType.behavioral,
            source_kind=source_kind,
            source_id=source_id,
            user_id=user_id,
            pet_id=pet_id,
            title=title,
            content=content,
            embedding=vector,
            metadata=metadata,
            occurred_at=occurred_at,
        )
    except Exception as exc:
        logger.warning("behavioral_memory_upsert_error", extra={"error": str(exc)[:200]})
        return None


async def upsert_cognitive_memory(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    source_kind: str,
    source_id: uuid.UUID,
    content: str,
    pet_id: uuid.UUID | None = None,
    title: str = "",
    metadata: dict | None = None,
    occurred_at: datetime | None = None,
    embed: EmbedFn = embed_text,
) -> MemoryNode | None:
    try:
        vector = await embed(content)
        return await _upsert_node(
            db=db,
            node_type=MemoryNodeType.cognitive,
            source_kind=source_kind,
            source_id=source_id,
            user_id=user_id,
            pet_id=pet_id,
            title=title,
            content=content,
            embedding=vector,
            metadata=metadata,
            occurred_at=occurred_at,
        )
    except Exception as exc:
        logger.warning("cognitive_memory_upsert_error", extra={"error": str(exc)[:200]})
        return None


async def upsert_knowledge_memory(
    *,
    db: AsyncSession,
    title: str,
    content: str,
    species: str = "all",
    category: str = "",
    url: str | None = None,
    source_id: uuid.UUID | None = None,
    metadata: dict | None = None,
    embed: EmbedFn = embed_text,
) -> MemoryNode | None:
    try:
        source_id = source_id or uuid.uuid5(uuid.NAMESPACE_URL, f"{title}|{species}|{url or ''}")
        meta = {"species": species, "category": category, "url": url}
        if metadata:
            meta.update(metadata)
        vector = await embed(f"{title}\n{content}")
        return await _upsert_node(
            db=db,
            node_type=MemoryNodeType.knowledge,
            source_kind="knowledge_article",
            source_id=source_id,
            title=title,
            content=content,
            embedding=vector,
            metadata=meta,
        )
    except Exception as exc:
        logger.warning("knowledge_memory_upsert_error", extra={"error": str(exc)[:200]})
        return None


async def delete_memory_for_source(
    *,
    db: AsyncSession,
    source_kind: str,
    source_id: uuid.UUID,
    node_type: MemoryNodeType | None = None,
) -> None:
    filters = [
        MemoryNode.source_kind == source_kind,
        MemoryNode.source_id == source_id,
    ]
    if node_type is not None:
        filters.append(MemoryNode.node_type == node_type)

    subq = select(MemoryNode.id).where(*filters).subquery()
    await db.execute(
        delete(MemoryEdge).where(
            or_(
                MemoryEdge.source_node_id.in_(select(subq.c.id)),
                MemoryEdge.target_node_id.in_(select(subq.c.id)),
            )
        )
    )
    await db.execute(delete(MemoryNode).where(*filters))
    await db.commit()
