import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.config import settings
from app.database import get_db
from app.models import Chat, ChatSession
from app.schemas.chat import (
    ChatMessageResponse,
    ChatSessionResponse,
    SaveSessionResponse,
    SavedSessionsResponse,
    SessionItem,
    TempSaveResponse,
    ResumeResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat-history"])


async def _generate_title(messages: list) -> str:
    """Generate a short title for a chat session using LLM."""
    from app.models import MessageRole
    recent = [m for m in messages if m.role == MessageRole.user][-5:]
    if not recent:
        return "对话"

    content = "\n".join(f"- {m.content[:100]}" for m in recent)
    prompt = f"用5-10个中文字概括这段对话的主题，只输出标题，不要引号：\n{content}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.model_api_base}/chat/completions",
                headers={"Authorization": f"Bearer {settings.model_api_key}"},
                json={
                    "model": settings.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 20,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            title = resp.json()["choices"][0]["message"]["content"].strip()
            return title[:50]
    except Exception as e:
        logger.warning(f"Title generation failed: {e}")
        return "对话记录"


@router.get("/history", response_model=list[ChatMessageResponse])
async def get_history(
    session_id: str | None = Query(None),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if session_id:
        sid = uuid.UUID(session_id)
    else:
        # Default to today's session
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.user_id == user_id,
                ChatSession.session_date == date.today(),
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            return []
        sid = session.id

    result = await db.execute(
        select(Chat)
        .where(Chat.session_id == sid, Chat.user_id == user_id)
        .order_by(Chat.created_at)
    )
    messages = result.scalars().all()
    return [
        ChatMessageResponse(
            id=str(m.id),
            role=m.role.value,
            content=m.content,
            cards=json.loads(m.cards_json) if m.cards_json else None,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


@router.get("/sessions/saved", response_model=SavedSessionsResponse)
async def get_saved_sessions(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    msg_count = (
        select(func.count(Chat.id))
        .where(Chat.session_id == ChatSession.id)
        .correlate(ChatSession)
        .scalar_subquery()
    )

    saved_result = await db.execute(
        select(ChatSession, msg_count.label("message_count"))
        .where(ChatSession.user_id == user_id, ChatSession.is_saved == True)
        .order_by(ChatSession.session_date.desc())
    )
    saved = [
        SessionItem(
            id=str(r.ChatSession.id),
            title=r.ChatSession.title,
            session_date=r.ChatSession.session_date.isoformat(),
            expires_at=None,
            is_saved=True,
            message_count=r.message_count,
        )
        for r in saved_result.all()
    ]

    recent_result = await db.execute(
        select(ChatSession, msg_count.label("message_count"))
        .where(
            ChatSession.user_id == user_id,
            ChatSession.is_saved == False,
            ChatSession.expires_at != None,
            ChatSession.expires_at > now,
        )
        .order_by(ChatSession.expires_at.desc())
    )
    recent = [
        SessionItem(
            id=str(r.ChatSession.id),
            title=None,
            session_date=r.ChatSession.session_date.isoformat(),
            expires_at=r.ChatSession.expires_at.isoformat() if r.ChatSession.expires_at else None,
            is_saved=False,
            message_count=r.message_count,
        )
        for r in recent_result.all()
    ]

    return SavedSessionsResponse(saved=saved, recent=recent)


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # Subquery for message count
    msg_count = (
        select(func.count(Chat.id))
        .where(Chat.session_id == ChatSession.id)
        .correlate(ChatSession)
        .scalar_subquery()
    )

    result = await db.execute(
        select(ChatSession, msg_count.label("message_count"))
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.session_date.desc())
        .limit(30)
    )

    return [
        ChatSessionResponse(
            id=str(row.ChatSession.id),
            session_date=row.ChatSession.session_date.isoformat(),
            created_at=row.ChatSession.created_at.isoformat(),
            message_count=row.message_count,
            is_saved=row.ChatSession.is_saved,
            title=row.ChatSession.title,
            expires_at=row.ChatSession.expires_at.isoformat() if row.ChatSession.expires_at else None,
        )
        for row in result.all()
    ]


@router.post("/sessions/{session_id}/save", response_model=SaveSessionResponse)
async def save_session(
    session_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    sid = uuid.UUID(session_id)
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == sid, ChatSession.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    msg_result = await db.execute(
        select(Chat).where(Chat.session_id == sid).order_by(Chat.created_at)
    )
    messages = msg_result.scalars().all()
    title = await _generate_title(messages)

    session.is_saved = True
    session.title = title
    session.expires_at = None
    await db.commit()

    return SaveSessionResponse(title=title, is_saved=True)


@router.post("/sessions/{session_id}/temp-save", response_model=TempSaveResponse)
async def temp_save_session(
    session_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    sid = uuid.UUID(session_id)
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == sid, ChatSession.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.is_saved:
        return TempSaveResponse(expires_at=session.created_at.isoformat(), is_saved=True)

    session.expires_at = datetime.now(timezone.utc) + timedelta(days=3)
    await db.commit()

    return TempSaveResponse(expires_at=session.expires_at.isoformat(), is_saved=False)


@router.post("/sessions/{session_id}/resume", response_model=ResumeResponse)
async def resume_session(
    session_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    sid = uuid.UUID(session_id)
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == sid, ChatSession.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    msg_result = await db.execute(
        select(Chat).where(Chat.session_id == sid).order_by(Chat.created_at)
    )
    messages = msg_result.scalars().all()

    return ResumeResponse(
        session_id=str(sid),
        messages=[
            ChatMessageResponse(
                id=str(m.id),
                role=m.role.value,
                content=m.content,
                cards=json.loads(m.cards_json) if m.cards_json else None,
                created_at=m.created_at.isoformat(),
            )
            for m in messages
        ],
    )
