"""Chat SSE endpoint — streams LLM responses to the frontend."""

import asyncio
import json
import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agents.emergency import build_emergency_hint, detect_emergency
from app.agents.orchestrator import run_orchestrator
from app.agents.pending_actions import pop_action
from app.agents.pre_processor import pre_process
from app.agents.prompts_v2 import build_messages, build_system_prompt
from app.agents.context_agent import trigger_summary_if_needed
from app.agents.tools import execute_tool
from app.auth import get_current_user_id
from app.config import settings
from app.database import get_db
from app.models import Chat, ChatSession, MessageRole, Pet

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chat"])

MAX_CONTEXT_MESSAGES = 5

# ---------- Image intent detection ----------
# If the user's text is clearly a tool command (avatar, log event with photo),
# skip sending images to the LLM (saves tokens + latency).
# Only send images to LLM when user asks about the image content or has no text.

import re

_IMAGE_TOOL_PATTERNS = re.compile(
    r"换头像|设为头像|改头像|设头像|用这张.*头像|头像.*换|头像.*设"
    r"|set.*avatar|change.*avatar|use.*avatar"
    r"|记录|记一下|拍了|拍的|拍照|存一下|保存"
    r"|log.*this|record.*this|save.*photo",
    re.IGNORECASE,
)


def _images_needed_for_llm(message: str) -> bool:
    """Determine if images should be sent to the LLM for understanding.

    Returns False when the text is a clear tool command (avatar/log) —
    images go directly to the tool executor, not through LLM vision.
    Returns True when the user asks about image content or sends no text.
    """
    text = message.strip()
    if not text:
        # No text — user wants LLM to look at the image
        return True
    if _IMAGE_TOOL_PATTERNS.search(text):
        # Tool command — images bypass LLM, go straight to executor
        return False
    # Default: send images to LLM (user might be asking about the image)
    return True

# Background task tracking — prevents garbage collection of fire-and-forget tasks
_bg_tasks: set[asyncio.Task] = set()


def _track_task(coro):
    """Create a tracked background task."""
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    location: dict | None = None  # {"lat": float, "lng": float}
    language: str | None = None   # "zh", "en", or None (auto-detect from message)
    images: list[str] | None = None  # base64-encoded JPEG strings


class ConfirmActionRequest(BaseModel):
    action_id: str


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


async def _get_recent_messages(
    db: AsyncSession, session_id: uuid.UUID, limit: int = 5
) -> list[Chat]:
    """Load recent messages from the session (unsummarized only, max limit)."""
    result = await db.execute(
        select(Chat)
        .where(Chat.session_id == session_id)
        .order_by(Chat.created_at.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


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


async def _event_generator(
    request: ChatRequest, user_id: uuid.UUID, db: AsyncSession
):
    # 1. Get or create today's session
    session = await _get_or_create_session(db, user_id)
    session_id = str(session.id)

    # 2. Save user message
    await _save_message(db, session.id, user_id, MessageRole.user, request.message)

    # --- Phase 1: Parallel preprocessing ---

    # Stage 1: Parallel DB queries
    pets, _ = await asyncio.gather(
        _get_pets(db, user_id),
        db.refresh(session),  # ensure context_summary is loaded
    )

    # Stage 2: Sync operations (fast, no await needed)
    emergency_result = detect_emergency(request.message)
    suggested_actions = pre_process(request.message, pets)

    if emergency_result.detected:
        logger.info("emergency_keywords_detected", extra={
            "session_id": session_id,
            "user_id": str(user_id),
            "keywords": emergency_result.keywords,
        })

    # Stage 3: Get recent messages (max 5)
    context_messages = await _get_recent_messages(db, session.id, limit=MAX_CONTEXT_MESSAGES)

    # --- Phase 2: Build prompt ---

    # Build emergency hint
    emergency_hint = (
        build_emergency_hint(emergency_result.keywords)
        if emergency_result.detected
        else None
    )

    # Build preprocessor hints
    preprocessor_hints = []
    for action in suggested_actions:
        if action.confidence >= 0.5:
            preprocessor_hints.append(
                f"{action.tool_name}({json.dumps(action.arguments, ensure_ascii=False)})"
            )

    # Model selection
    is_emergency = emergency_result.detected
    model = settings.emergency_model if is_emergency else settings.orchestrator_model

    # Build system prompt (cache-friendly order)
    today_str = date.today().isoformat()
    system_prompt = build_system_prompt(
        pets=pets,
        session_summary=session.context_summary if session else None,
        emergency_hint=emergency_hint,
        preprocessor_hints=preprocessor_hints if preprocessor_hints else None,
        today=today_str,
    )

    # Image routing: only send images to LLM when needed for understanding
    has_images = bool(request.images)
    if has_images and _images_needed_for_llm(request.message):
        llm_images = request.images    # LLM needs to see the images
        tool_images = request.images   # tools also get them
    elif has_images:
        llm_images = None              # skip LLM vision (save tokens)
        tool_images = request.images   # tools still get the images (avatar/photo upload)
    else:
        llm_images = None
        tool_images = None

    # Build messages
    recent_msgs = [{"role": m.role.value, "content": m.content} for m in context_messages]
    messages = build_messages(recent_msgs, request.message, images=llm_images)

    # --- Phase 3: Run orchestrator via queue ---

    queue: asyncio.Queue = asyncio.Queue()

    async def on_token(text):
        await queue.put({"event": "token", "data": json.dumps({"text": text})})

    async def on_card(card_data):
        await queue.put({"event": "card", "data": json.dumps(card_data)})

    async def _run_orchestrator_to_queue():
        try:
            result = await run_orchestrator(
                message=request.message,
                system_prompt=system_prompt,
                context_messages=messages,  # recent history + current user message
                model=model,
                db=db,
                user_id=user_id,
                session_id=session.id,
                on_token=on_token,
                on_card=on_card,
                today=today_str,
                location=request.location,
                images=tool_images,
            )
            await queue.put(("_result", result))
        except Exception as e:
            logger.error("orchestrator_error", extra={
                "error_type": type(e).__name__,
                "error_message": str(e)[:500],
            })
            error_text = f"Sorry, I'm having trouble right now. Please try again. (Error: {type(e).__name__})"
            await queue.put({"event": "token", "data": json.dumps({"text": error_text})})
            from app.agents.orchestrator import OrchestratorResult
            await queue.put(("_result", OrchestratorResult(response_text=error_text)))
        finally:
            await queue.put(_SENTINEL)

    task = asyncio.create_task(_run_orchestrator_to_queue())

    result = None
    while True:
        item = await queue.get()
        if item is _SENTINEL:
            break
        if isinstance(item, tuple) and item[0] == "_result":
            result = item[1]
            continue
        yield item

    await task

    # --- Phase 4: Post-response ---

    if result is None:
        from app.agents.orchestrator import OrchestratorResult
        result = OrchestratorResult()

    # Save assistant response
    all_cards = result.cards + result.confirm_cards
    cards_json = json.dumps(all_cards) if all_cards else None
    await _save_message(
        db, session.id, user_id, MessageRole.assistant,
        result.response_text, cards_json
    )

    # Trigger context compression if needed (async, non-blocking)
    _track_task(trigger_summary_if_needed(session.id, db))

    # Done event
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


@router.post("/chat/confirm-action")
async def confirm_action(
    request: ConfirmActionRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Execute a pending action that the user confirmed via card button.

    No LLM involved — direct tool execution from stored arguments.
    """
    action = pop_action(request.action_id, str(user_id))
    if not action:
        raise HTTPException(status_code=404, detail="Action not found or expired")

    try:
        result = await execute_tool(
            action.tool_name, action.arguments, db, user_id,
        )
        await db.commit()
    except Exception as exc:
        logger.error("confirm_action_error", extra={
            "action_id": action.action_id,
            "tool": action.tool_name,
            "error": str(exc)[:200],
        })
        raise HTTPException(status_code=500, detail=str(exc))

    # Save confirmation as assistant message in the chat
    session_id = uuid.UUID(action.session_id)
    card = result.get("card")
    cards_json = json.dumps([card]) if card else None
    await _save_message(
        db, session_id, user_id, MessageRole.assistant,
        action.description,
        cards_json,
    )

    return {
        "success": result.get("success", True),
        "card": card,
        "message": action.description,
    }
