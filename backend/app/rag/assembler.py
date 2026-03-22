"""RAG assembler — orchestrates retrieval, augmentation, and formatting."""

import asyncio
import logging
from uuid import UUID

from app.config import settings
from app.rag.base import RetrievalResult
from app.rag.calendar_retriever import CalendarRetriever
from app.rag.chat_retriever import ChatHistoryRetriever
from app.rag.embedder import get_embedding_service
from app.rag.summarizer import ensure_yesterday_summary

logger = logging.getLogger(__name__)

# Singleton retrievers
_chat_retriever = ChatHistoryRetriever()
_calendar_retriever = CalendarRetriever()


async def assemble_rag_context(
    message: str,
    user_id: UUID,
    pet_id: UUID | None = None,
) -> str:
    """Main entry point: embed query -> retrieve -> augment -> format.

    Returns formatted context string for prompt injection.
    Returns empty string on any failure.
    """
    # Step 1: Generate query embedding + ensure yesterday's summary (parallel)
    embed_task = get_embedding_service().embed(message)
    summary_task = ensure_yesterday_summary(user_id)

    query_embedding, _ = await asyncio.gather(embed_task, summary_task, return_exceptions=True)

    if query_embedding is None or isinstance(query_embedding, Exception):
        logger.warning("rag_skipped_no_embedding")
        return ""

    # Step 2: Parallel retrieval with timeout
    try:
        chat_results, cal_results = await asyncio.wait_for(
            asyncio.gather(
                _chat_retriever.retrieve(query_embedding, user_id, top_k=10, pet_id=pet_id),
                _calendar_retriever.retrieve(query_embedding, user_id, top_k=10, pet_id=pet_id),
                return_exceptions=True,
            ),
            timeout=settings.rag_retrieval_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("rag_retrieval_timeout")
        return ""

    # Collect valid results (skip exceptions)
    all_results: list[RetrievalResult] = []
    if isinstance(chat_results, list):
        all_results.extend(chat_results)
    if isinstance(cal_results, list):
        all_results.extend(cal_results)

    if not all_results:
        return ""

    # Step 3: Filter by score threshold
    all_results = [r for r in all_results if r.score >= settings.rag_score_threshold]
    if not all_results:
        return ""

    # Step 4: Augmentation
    all_results = _deduplicate(all_results)

    # Separate by type for budget truncation
    chat = [r for r in all_results if r.source_type in ("chat_turn", "daily_summary")]
    calendar = [r for r in all_results if r.source_type == "calendar_event"]

    chat = _truncate_by_budget(chat, settings.rag_chat_token_budget)
    calendar = _truncate_by_budget(calendar, settings.rag_calendar_token_budget)

    # Step 5: Format
    return _format_context(chat + calendar)


def _deduplicate(results: list[RetrievalResult]) -> list[RetrievalResult]:
    """If a summary and a chat turn cover the same day, keep the higher-scored one."""
    # Find dates covered by summaries and their best scores
    summary_scores: dict[str, float] = {}
    for r in results:
        if r.source_type == "daily_summary" and r.metadata.get("session_date"):
            d = r.metadata["session_date"]
            summary_scores[d] = max(summary_scores.get(d, 0), r.score)

    return [
        r for r in results
        if not (
            r.source_type == "chat_turn"
            and r.metadata.get("session_date") in summary_scores
            and summary_scores[r.metadata["session_date"]] >= r.score
        )
    ]


def _truncate_by_budget(
    results: list[RetrievalResult], max_tokens: int
) -> list[RetrievalResult]:
    """Keep highest-scoring results within token budget.

    Token estimation: len(text) // 2 (works for Chinese and English).
    """
    results.sort(key=lambda r: r.score, reverse=True)
    kept = []
    used = 0
    for r in results:
        tokens = len(r.content) // 2
        if used + tokens > max_tokens:
            break
        kept.append(r)
        used += tokens
    return kept


def _format_context(results: list[RetrievalResult]) -> str:
    """Format retrieval results into a markdown section for the prompt."""
    if not results:
        return ""

    chat_items = [r for r in results if r.source_type in ("chat_turn", "daily_summary")]
    cal_items = [r for r in results if r.source_type == "calendar_event"]

    # Sort by date
    chat_items.sort(key=lambda r: r.metadata.get("session_date", ""), reverse=True)
    cal_items.sort(key=lambda r: r.metadata.get("event_date", ""), reverse=True)

    sections = ["## Relevant History"]

    if chat_items:
        sections.append("\n### Recent conversations")
        for r in chat_items:
            date_str = r.metadata.get("session_date", "")
            prefix = f"[{date_str}] " if date_str else ""
            sections.append(f"- {prefix}{r.content}")

    if cal_items:
        sections.append("\n### Calendar records")
        for r in cal_items:
            sections.append(f"- {r.content}")

    return "\n".join(sections)
