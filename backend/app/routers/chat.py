"""Chat SSE endpoint — streams LLM responses to the frontend."""

import json
import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agents.emergency import detect_emergency
from app.agents.prompts import CHAT_SYSTEM_PROMPT
from app.agents.router import route_intent
from app.auth import get_current_user_id
from app.config import settings
from app.database import get_db
from app.models import Chat, ChatSession, MessageRole, Pet

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chat"])

MAX_CONTEXT_MESSAGES = 20


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    location: dict | None = None  # {"lat": float, "lng": float}


async def _get_or_create_session(
    db: AsyncSession, user_id: uuid.UUID
) -> ChatSession:
    """Find today's session or create a new one."""
    today = date.today()
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.user_id == user_id,
            ChatSession.session_date == today,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        session = ChatSession(
            id=uuid.uuid4(), user_id=user_id, session_date=today
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
    return session


async def _build_pet_context(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Build pet profile context string for the system prompt."""
    result = await db.execute(
        select(Pet).where(Pet.user_id == user_id).order_by(Pet.created_at)
    )
    pets = result.scalars().all()
    if not pets:
        return "The user has not added any pets yet."

    lines = ["The user's pets:"]
    for p in pets:
        parts = [f"- {p.name}: {p.species.value}"]
        if p.breed:
            parts.append(f", breed: {p.breed}")
        if p.weight:
            parts.append(f", weight: {p.weight}kg")
        if p.birthday:
            parts.append(f", birthday: {p.birthday.isoformat()}")
        lines.append("".join(parts))
    return "\n".join(lines)


async def _get_context_messages(
    db: AsyncSession, session_id: uuid.UUID
) -> list[dict]:
    """Load recent messages from the session for LLM context."""
    result = await db.execute(
        select(Chat)
        .where(Chat.session_id == session_id)
        .order_by(Chat.created_at.desc())
        .limit(MAX_CONTEXT_MESSAGES)
    )
    messages = list(reversed(result.scalars().all()))
    return [{"role": m.role.value, "content": m.content} for m in messages]


async def _save_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    role: MessageRole,
    content: str,
    cards_json: str | None = None,
) -> Chat:
    msg = Chat(
        id=uuid.uuid4(),
        session_id=session_id,
        user_id=user_id,
        role=role,
        content=content,
        cards_json=cards_json,
    )
    db.add(msg)
    await db.commit()
    return msg


async def _event_generator(
    request: ChatRequest, user_id: uuid.UUID, db: AsyncSession
):
    # 1. Get or create today's session
    session = await _get_or_create_session(db, user_id)
    session_id = str(session.id)

    # 2. Save user message
    await _save_message(db, session.id, user_id, MessageRole.user, request.message)

    # 3. Emergency detection (non-blocking — emitted before chat response)
    is_emergency = detect_emergency(request.message)
    if is_emergency:
        logger.info("emergency_detected", extra={
            "session_id": session_id,
            "user_id": str(user_id),
            "message_preview": request.message[:100],
        })
        yield {
            "event": "emergency",
            "data": json.dumps({"message": "Possible emergency detected", "action": "find_er"}),
        }

    # 4. Build context
    pet_context = await _build_pet_context(db, user_id)
    system_msg = CHAT_SYSTEM_PROMPT.format(pet_context=pet_context)
    context_messages = await _get_context_messages(db, session.id)

    # 5. Route intent
    intent = await route_intent(request.message, context_messages)
    logger.info("intent_routed", extra={"session_id": session_id, "intent": intent})

    llm_messages = [{"role": "system", "content": system_msg}] + context_messages

    # 6. Stream from LLM (all intents use basic LLM proxy for now)
    full_response = ""
    logger.info("llm_stream_start", extra={
        "session_id": session_id,
        "user_id": str(user_id),
        "model": settings.strong_model,
        "context_messages": len(context_messages),
    })
    try:
        import litellm

        response = await litellm.acompletion(
            model=settings.strong_model,
            messages=llm_messages,
            stream=True,
        )

        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                full_response += delta.content
                yield {
                    "event": "token",
                    "data": json.dumps({"text": delta.content}),
                }

        logger.info("llm_stream_complete", extra={
            "session_id": session_id,
            "response_length": len(full_response),
        })

    except Exception as e:
        logger.error("llm_stream_error", extra={
            "session_id": session_id,
            "error_type": type(e).__name__,
            "error_message": str(e)[:500],
        })
        error_text = f"Sorry, I'm having trouble connecting right now. Please try again. (Error: {type(e).__name__})"
        full_response = error_text
        yield {
            "event": "token",
            "data": json.dumps({"text": error_text}),
        }

    # 7. Save assistant response
    await _save_message(db, session.id, user_id, MessageRole.assistant, full_response)

    # 8. Done event with detected intent
    yield {
        "event": "done",
        "data": json.dumps({"intent": intent, "session_id": session_id}),
    }


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return EventSourceResponse(_event_generator(request, user_id, db))
