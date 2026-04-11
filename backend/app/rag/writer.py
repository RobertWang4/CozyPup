"""Async embedding writer — generates and stores embeddings after chat."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Embedding, SourceType

logger = logging.getLogger(__name__)


async def write_chat_embedding(
    db: AsyncSession,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    content: str,
    pet_id: uuid.UUID | None = None,
    source_type: SourceType = SourceType.daily_summary,
    metadata: dict | None = None,
) -> None:
    """Generate embedding for content and store in DB. Fails silently."""
    from app.rag.embeddings import embed_text  # lazy import to avoid circular deps
    try:
        vector = await embed_text(content)
        emb = Embedding(
            user_id=user_id,
            pet_id=pet_id,
            source_type=source_type,
            source_id=source_id,
            content=content,
            embedding=vector,
            metadata_json=metadata,
        )
        db.add(emb)
        await db.commit()
        logger.info("embedding_written", extra={
            "source_type": source_type.value,
            "content_length": len(content),
        })
    except Exception as exc:
        logger.warning("embedding_write_error", extra={"error": str(exc)[:200]})
