"""Lazy daily summary generator — runs on next day's first message if needed."""

import asyncio
import logging
import uuid
from datetime import date, timedelta

import litellm
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Chat, ChatSession, DailySummary, Embedding, SourceType
from app.rag.embedder import get_embedding_service

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = """Summarize this conversation between a pet owner and their AI assistant.
Focus on: health events, decisions made, pet info mentioned, action items.
Keep it under 200 words. Write in the same language as the conversation.

Conversation:
{conversation}"""


async def ensure_yesterday_summary(user_id: uuid.UUID) -> None:
    """Check if yesterday has a summary; if not, generate and store one.

    Silently fails — never impacts the current chat.
    """
    try:
        yesterday = date.today() - timedelta(days=1)
        async with async_session() as db:
            # Check if summary already exists
            result = await db.execute(
                select(DailySummary).where(
                    DailySummary.user_id == user_id,
                    DailySummary.session_date == yesterday,
                )
            )
            if result.scalar_one_or_none() is not None:
                return  # Already exists

            # Find yesterday's session
            result = await db.execute(
                select(ChatSession).where(
                    ChatSession.user_id == user_id,
                    ChatSession.session_date == yesterday,
                )
            )
            session = result.scalar_one_or_none()
            if session is None:
                return  # No conversation yesterday

            # Load yesterday's messages
            result = await db.execute(
                select(Chat)
                .where(Chat.session_id == session.id)
                .order_by(Chat.created_at)
            )
            messages = result.scalars().all()
            if not messages:
                return

            # Build conversation text
            conversation = "\n".join(
                f"{m.role.value}: {m.content}" for m in messages if m.content
            )
            if len(conversation) < 20:
                return  # Too short to summarize

            # Generate summary via LLM
            summary_text = await _generate_summary(conversation)
            if not summary_text:
                return

            # Store summary
            summary = DailySummary(
                id=uuid.uuid4(),
                user_id=user_id,
                session_id=session.id,
                session_date=yesterday,
                summary=summary_text,
            )
            db.add(summary)

            # Embed and store
            embedding = await get_embedding_service().embed(summary_text)
            if embedding:
                emb_record = Embedding(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    source_type=SourceType.daily_summary,
                    source_id=summary.id,
                    content=summary_text,
                    embedding=embedding,
                    metadata_json={"session_date": yesterday.isoformat()},
                )
                db.add(emb_record)

            await db.commit()
            logger.info("daily_summary_generated", extra={"session_date": yesterday.isoformat()})

    except Exception as exc:
        logger.warning("daily_summary_error", extra={"error": str(exc)[:200]})


async def _generate_summary(conversation: str) -> str | None:
    """Call LLM to generate a conversation summary."""
    try:
        kwargs = dict(
            model=settings.default_model,
            messages=[{"role": "user", "content": _SUMMARY_PROMPT.format(conversation=conversation)}],
            temperature=0.2,
            max_tokens=300,
        )
        if settings.model_api_base:
            kwargs["api_base"] = settings.model_api_base
        if settings.model_api_key:
            kwargs["api_key"] = settings.model_api_key

        response = await asyncio.wait_for(
            litellm.acompletion(**kwargs),
            timeout=5.0,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("summary_llm_error", extra={"error": str(exc)[:200]})
        return None
