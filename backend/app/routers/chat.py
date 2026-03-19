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

from app.agents.chat_agent import ChatAgent
from app.agents.email_agent import EmailAgent
from app.agents.emergency import detect_emergency
from app.agents.map_agent import MapAgent
from app.agents.prompts import CHAT_SYSTEM_PROMPT
from app.agents.router import route_intent
from app.agents.summary_agent import SummaryAgent
from app.auth import get_current_user_id
from app.config import settings
from app.database import get_db
from app.models import Chat, ChatSession, MessageRole, Pet

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chat"])

MAX_CONTEXT_MESSAGES = 20

# Singleton agent instances
_chat_agent = ChatAgent()
_summary_agent = SummaryAgent()
_map_agent = MapAgent()
_email_agent = EmailAgent()


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


async def _get_pets(db: AsyncSession, user_id: uuid.UUID) -> list[Pet]:
    """Load all pets for the user."""
    result = await db.execute(
        select(Pet).where(Pet.user_id == user_id).order_by(Pet.created_at)
    )
    return list(result.scalars().all())


async def _build_pet_context(pets: list[Pet]) -> str:
    """Build pet profile context string for the system prompt."""
    if not pets:
        return "The user has not added any pets yet."

    lines = ["The user's pets:"]
    for p in pets:
        parts = [f"- {p.name} (id: {p.id}): {p.species.value}"]
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


async def _handle_chat(request, session, user_id, db, pets, context_messages):
    """Handle intent=chat via ChatAgent with streaming."""
    pet_context = await _build_pet_context(pets)
    system_msg = CHAT_SYSTEM_PROMPT.format(pet_context=pet_context)

    full_response = ""
    cards = []

    async def on_token(text):
        nonlocal full_response
        full_response += text

    async def on_card(card_data):
        cards.append(card_data)

    try:
        result = await _chat_agent.execute(
            request.message,
            {
                "system_prompt": system_msg,
                "context_messages": context_messages,
                "db": db,
                "user_id": user_id,
                "session_id": session.id,
            },
            on_token=on_token,
            on_card=on_card,
        )
        full_response = result.get("response", full_response)
        cards = result.get("cards", cards)
    except Exception as e:
        logger.error("chat_agent_error", extra={
            "error_type": type(e).__name__,
            "error_message": str(e)[:500],
        })
        full_response = f"Sorry, I'm having trouble right now. Please try again. (Error: {type(e).__name__})"

    return full_response, cards


async def _handle_summary(request, session, user_id, db, pets):
    """Handle intent=summarize via SummaryAgent."""
    try:
        result = await _summary_agent.execute(
            request.message,
            {
                "db": db,
                "user_id": user_id,
                "session_id": session.id,
                "pets": pets,
            },
        )
        return result.get("summary_text", ""), result.get("cards", [])
    except Exception as e:
        logger.error("summary_agent_error", extra={"error": str(e)[:500]})
        return "Sorry, I couldn't summarize the conversation right now.", []


async def _handle_map(request, user_id, pets):
    """Handle intent=map via MapAgent."""
    try:
        result = await _map_agent.execute(
            request.message,
            {
                "location": request.location,
                "pets": pets,
            },
        )
        response_text = result.get("response", "")
        card = result.get("card")
        return response_text, [card] if card else []
    except Exception as e:
        logger.error("map_agent_error", extra={"error": str(e)[:500]})
        return "Sorry, I couldn't search for locations right now.", []


async def _handle_email(request, user_id, db, session, pets, context_messages):
    """Handle intent=email via EmailAgent."""
    try:
        result = await _email_agent.execute(
            request.message,
            {
                "db": db,
                "user_id": user_id,
                "session_id": session.id,
                "pets": pets,
                "context_messages": context_messages,
            },
        )
        response_text = result.get("response", "")
        card = result.get("card")
        return response_text, [card] if card else []
    except Exception as e:
        logger.error("email_agent_error", extra={"error": str(e)[:500]})
        return "Sorry, I couldn't generate the email right now.", []


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

    # 4. Load shared context
    pets = await _get_pets(db, user_id)
    context_messages = await _get_context_messages(db, session.id)

    # 5. Route intent
    intent = await route_intent(request.message, context_messages)
    logger.info("intent_routed", extra={"session_id": session_id, "intent": intent})

    # 6. Dispatch to the appropriate agent
    cards = []
    if intent == "chat":
        full_response, cards = await _handle_chat(
            request, session, user_id, db, pets, context_messages
        )
    elif intent == "summarize":
        full_response, cards = await _handle_summary(
            request, session, user_id, db, pets
        )
    elif intent == "map":
        full_response, cards = await _handle_map(request, user_id, pets)
    elif intent == "email":
        full_response, cards = await _handle_email(
            request, user_id, db, session, pets, context_messages
        )
    else:
        full_response = "I'm not sure how to handle that. Could you rephrase?"

    # 7. Emit response tokens
    yield {
        "event": "token",
        "data": json.dumps({"text": full_response}),
    }

    # 8. Emit card events
    for card in cards:
        yield {
            "event": "card",
            "data": json.dumps(card),
        }

    # 9. Save assistant response
    cards_json = json.dumps(cards) if cards else None
    await _save_message(
        db, session.id, user_id, MessageRole.assistant, full_response, cards_json
    )

    # 10. Done event with detected intent
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
