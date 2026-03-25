"""
Context Agent: compresses chat history into structured summaries.
Triggered lazily (when unsummarized messages >= 5), runs async without blocking.
"""
import json
import logging
from datetime import datetime

import litellm

from app.config import settings

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """你是一个对话摘要助手。请将以下对话历史压缩为结构化摘要。

要求:
1. 提取关键话题和事实
2. 记录未完成的事项
3. 捕捉用户的情绪状态
4. 保留重要的具体信息（数字、日期、宠物名等）

输出 JSON 格式:
{
  "topics": ["话题1", "话题2"],
  "pending": "未完成的事项描述，如果没有则为null",
  "mood": "用户情绪描述",
  "key_facts": ["事实1", "事实2", ...]
}

只输出 JSON，不要其他内容。"""


async def summarize_context(
    messages: list[dict],
    previous_summary: dict | None = None,
) -> dict:
    """Call cheap LLM to summarize messages into structured format."""

    user_content = ""
    if previous_summary:
        user_content += f"上次摘要:\n{json.dumps(previous_summary, ensure_ascii=False)}\n\n"

    user_content += "新的对话记录:\n"
    for msg in messages:
        role = "用户" if msg.get("role") == "user" else "助手"
        content = msg.get("content", "")
        if isinstance(content, list):  # multimodal message
            content = " ".join(
                part.get("text", "[图片]") for part in content
                if isinstance(part, dict)
            )
        user_content += f"{role}: {content}\n"

    try:
        response = await litellm.acompletion(
            model=settings.context_model,
            messages=[
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
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
    summary = await summarize_context(messages, previous)

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
