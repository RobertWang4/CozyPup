"""Chat SSE endpoint — streams LLM responses to the frontend."""

import asyncio
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
from app.agents.emergency import detect_emergency
from app.agents.prompts import CHAT_SYSTEM_PROMPT
from app.auth import get_current_user_id
from app.database import get_db
from app.models import Chat, ChatSession, MessageRole, Pet

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chat"])

MAX_CONTEXT_MESSAGES = 20

_chat_agent = ChatAgent()


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    location: dict | None = None  # {"lat": float, "lng": float}
    language: str | None = None   # "zh", "en", or None (auto-detect from message)


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
        info = [f"- {p.name} (id: {p.id}): {p.species.value}"]
        if p.breed:
            info.append(f"breed={p.breed}")
        if p.weight:
            info.append(f"weight={p.weight}kg")
        if p.birthday:
            info.append(f"birthday={p.birthday.isoformat()}")
        lines.append(", ".join(info))
        if p.profile:
            profile_str = json.dumps(p.profile, ensure_ascii=False)
            lines.append(f"  Profile: {profile_str}")
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


_SENTINEL = object()


async def _run_chat_agent_to_queue(
    queue: asyncio.Queue,
    request: ChatRequest,
    session: ChatSession,
    user_id: uuid.UUID,
    db: AsyncSession,
    pets: list[Pet],
    context_messages: list[dict],
):
    """Run ChatAgent, pushing SSE events into the queue."""
    pet_context = await _build_pet_context(pets)
    system_msg = CHAT_SYSTEM_PROMPT.format(
        pet_context=pet_context, today_date=date.today().isoformat()
    )

    async def on_token(text):
        await queue.put({"event": "token", "data": json.dumps({"text": text})})

    async def on_card(card_data):
        await queue.put({"event": "card", "data": json.dumps(card_data)})

    try:
        result = await _chat_agent.execute(
            request.message,
            {
                "system_prompt": system_msg,
                "context_messages": context_messages,
                "db": db,
                "user_id": user_id,
                "session_id": session.id,
                "location": request.location,
            },
            on_token=on_token,
            on_card=on_card,
        )
        await queue.put(("_result", result))
    except Exception as e:
        logger.error("chat_agent_error", extra={
            "error_type": type(e).__name__,
            "error_message": str(e)[:500],
        })
        error_text = f"Sorry, I'm having trouble right now. Please try again. (Error: {type(e).__name__})"
        await queue.put({"event": "token", "data": json.dumps({"text": error_text})})
        await queue.put(("_result", {"response": error_text, "cards": []}))
    finally:
        await queue.put(_SENTINEL)


async def _event_generator(
    request: ChatRequest, user_id: uuid.UUID, db: AsyncSession
):
    # 1. Get or create today's session
    session = await _get_or_create_session(db, user_id)
    session_id = str(session.id)

    # 2. Save user message
    await _save_message(db, session.id, user_id, MessageRole.user, request.message)

    # 3. Emergency detection (non-blocking — emitted before chat response)
    if detect_emergency(request.message):
        logger.info("emergency_detected", extra={
            "session_id": session_id,
            "user_id": str(user_id),
        })
        yield {
            "event": "emergency",
            "data": json.dumps({"message": "Possible emergency detected", "action": "find_er"}),
        }

    # 4. Load context
    pets = await _get_pets(db, user_id)
    context_messages = await _get_context_messages(db, session.id)

    # 5. Stream ChatAgent response
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(
        _run_chat_agent_to_queue(
            queue, request, session, user_id, db, pets, context_messages
        )
    )

    result = {"response": "", "cards": []}
    while True:
        item = await queue.get()
        if item is _SENTINEL:
            break
        if isinstance(item, tuple) and item[0] == "_result":
            result = item[1]
            continue
        yield item

    await task
    full_response = result.get("response", "")
    cards = result.get("cards", [])

    # 6. Save assistant response
    cards_json = json.dumps(cards) if cards else None
    await _save_message(
        db, session.id, user_id, MessageRole.assistant, full_response, cards_json
    )

    # 7. Done event
    yield {
        "event": "done",
        "data": json.dumps({"intent": "chat", "session_id": session_id}),
    }


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return EventSourceResponse(_event_generator(request, user_id, db))
