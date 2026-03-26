"""
Context Agent: compresses chat history into structured summaries.
Triggered lazily (when unsummarized messages >= 5), runs async without blocking.
"""
import json
import logging
from datetime import datetime

import litellm

from app.agents.locale import t
from app.config import settings

logger = logging.getLogger(__name__)


async def summarize_context(
    messages: list[dict],
    previous_summary: dict | None = None,
    lang: str = "zh",
) -> dict:
    """Call cheap LLM to summarize messages into structured format."""

    user_content = ""
    if previous_summary:
        user_content += f"{t('previous_summary_label', lang)}:\n{json.dumps(previous_summary, ensure_ascii=False)}\n\n"

    user_content += f"{t('new_messages_label', lang)}:\n"
    for msg in messages:
        role = t("role_user", lang) if msg.get("role") == "user" else t("role_assistant", lang)
        content = msg.get("content", "")
        if isinstance(content, list):  # multimodal message
            content = " ".join(
                part.get("text", "[图片]") for part in content
                if isinstance(part, dict)
            )
        user_content += f"{role}: {content}\n"

    try:
        from app.agents import llm_extra_kwargs
        response = await litellm.acompletion(
            model=settings.context_model,
            messages=[
                {"role": "system", "content": t("summary_system_prompt", lang)},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            **llm_extra_kwargs(),
        )

        raw = response.choices[0].message.content
        summary = json.loads(raw)

        # Validate expected keys
        for key in ("topics", "key_facts"):
            if key not in summary or not isinstance(summary[key], list):
                summary[key] = []
        if "pending" not in summary:
            summary["pending"] = None
        if "mood" not in summary:
            summary["mood"] = "neutral"

        return summary
    except Exception as exc:
        logger.error("context_agent_error", extra={"error": str(exc)})
        return {
            "topics": [],
            "pending": None,
            "mood": "unknown",
            "key_facts": [],
        }


def should_summarize(
    total_messages: int,
    summarized_up_to: int | None,
    threshold: int = 5,
) -> bool:
    """Check if we have enough unsummarized messages to trigger summary."""
    last_summarized = summarized_up_to or 0
    unsummarized = total_messages - last_summarized
    return unsummarized >= threshold


async def trigger_summary_if_needed(
    session_id,
    db,
    threshold: int = 5,
    lang: str = "zh",
):
    """
    Check if summary is needed and run it async (non-blocking).
    Called after response is sent to user.
    """
    from app.models import ChatSession, Chat
    from sqlalchemy import select, func

    # Get session
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        return

    # Count total messages
    count_result = await db.execute(
        select(func.count(Chat.id)).where(Chat.session_id == session_id)
    )
    total = count_result.scalar() or 0

    if not should_summarize(total, session.summarized_up_to, threshold):
        return

    # Load unsummarized messages
    query = select(Chat).where(Chat.session_id == session_id).order_by(Chat.created_at)
    if session.summarized_up_to:
        query = query.offset(session.summarized_up_to)

    result = await db.execute(query)
    chats = result.scalars().all()

    messages = [
        {"role": chat.role.value, "content": chat.content}
        for chat in chats
    ]

    if not messages:
        return

    # Summarize
    previous = session.context_summary
    summary = await summarize_context(messages, previous, lang=lang)

    # Update session
    session.context_summary = summary
    session.summarized_up_to = total
    await db.commit()

    logger.info(
        "context_summary_updated",
        extra={
            "session_id": str(session_id),
            "total_messages": total,
            "topics": summary.get("topics", []),
        },
    )
