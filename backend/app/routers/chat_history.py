import json
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.models import Chat, ChatSession
from app.schemas.chat import ChatMessageResponse, ChatSessionResponse

router = APIRouter(prefix="/api/v1/chat", tags=["chat-history"])


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
        )
        for row in result.all()
    ]
