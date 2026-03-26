"""Chat SSE endpoint — streams LLM responses to the frontend."""

import asyncio
import base64
import json
import logging
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agents.emergency import build_emergency_hint, detect_emergency
from app.agents.locale import detect_language
from app.agents.orchestrator import run_orchestrator
from app.agents.pending_actions import pop_action
from app.agents.post_processor import response_claims_action, execute_suggested_actions
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
MAX_IMAGE_CONTEXT_MESSAGES = 3  # max past messages with images to inject into LLM context

PHOTO_DIR = Path("/app/uploads/photos") if Path("/app/uploads").exists() else Path(__file__).resolve().parent.parent / "uploads" / "photos"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)


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


def _save_images_to_disk(images_b64: list[str]) -> list[str]:
    """Save base64 images to disk, return URL paths."""
    urls = []
    for img_b64 in images_b64:
        try:
            image_data = base64.b64decode(img_b64)
            if len(image_data) > 5 * 1024 * 1024:
                continue
            photo_id = uuid.uuid4()
            filename = f"{photo_id}.jpg"
            (PHOTO_DIR / filename).write_bytes(image_data)
            urls.append(f"/api/v1/calendar/photos/{filename}")
        except Exception:
            continue
    return urls


async def _save_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    role: MessageRole,
    content: str,
    cards_json: str | None = None,
    image_urls: list[str] | None = None,
) -> Chat:
    msg = Chat(
        id=uuid.uuid4(),
        session_id=session_id,
        user_id=user_id,
        role=role,
        content=content,
        cards_json=cards_json,
        image_urls=image_urls,
    )
    db.add(msg)
    await db.commit()
    return msg


def _build_context_with_images(context_messages: list[Chat]) -> list[dict]:
    """Build context message list, injecting images for the most recent N messages that have them."""
    msgs = []
    # Count image messages from the end to find the most recent ones
    image_msg_count = 0
    image_msg_indices: set[int] = set()
    for i in range(len(context_messages) - 1, -1, -1):
        m = context_messages[i]
        if m.image_urls and image_msg_count < MAX_IMAGE_CONTEXT_MESSAGES:
            image_msg_indices.add(i)
            image_msg_count += 1

    for i, m in enumerate(context_messages):
        if i in image_msg_indices and m.image_urls:
            # Load images from disk and build multimodal content
            # Include photo URLs as text so LLM can reference them in tool calls
            url_hint = " ".join(f"[photo_url: {u}]" for u in m.image_urls)
            content_parts: list[dict] = [{"type": "text", "text": f"{m.content}\n{url_hint}"}]
            for url in m.image_urls:
                # url is like "/api/v1/calendar/photos/xxx.jpg"
                filename = url.split("/")[-1]
                filepath = PHOTO_DIR / filename
                if filepath.exists():
                    img_b64 = base64.b64encode(filepath.read_bytes()).decode()
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    })
            msgs.append({"role": m.role.value, "content": content_parts})
        else:
            msgs.append({"role": m.role.value, "content": m.content})

    return msgs


_SENTINEL = object()


async def _event_generator(
    request: ChatRequest, user_id: uuid.UUID, db: AsyncSession
):
    # 1. Get or create today's session
    session = await _get_or_create_session(db, user_id)
    session_id = str(session.id)

    # 2. Save user message (with image URLs if present)
    saved_image_urls = None
    if request.images:
        saved_image_urls = _save_images_to_disk(request.images)
    await _save_message(
        db, session.id, user_id, MessageRole.user, request.message,
        image_urls=saved_image_urls or None,
    )

    # --- Phase 1: Parallel preprocessing ---

    # Stage 1: Sequential DB queries (async sessions don't support concurrent ops)
    pets = await _get_pets(db, user_id)
    await db.refresh(session)  # ensure context_summary is loaded

    # Stage 2: Sync operations (fast, no await needed)
    lang = request.language or detect_language(request.message)
    emergency_result = detect_emergency(request.message)
    suggested_actions = pre_process(request.message, pets, lang=lang)

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
        build_emergency_hint(emergency_result.keywords, lang=lang)
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
    model = settings.emergency_model if is_emergency else settings.model

    # Build system prompt (cache-friendly order)
    today_str = date.today().isoformat()
    system_prompt = build_system_prompt(
        pets=pets,
        session_summary=session.context_summary if session else None,
        emergency_hint=emergency_hint,
        preprocessor_hints=preprocessor_hints if preprocessor_hints else None,
        today=today_str,
        lang=lang,
    )

    # Build messages — past images already in context via _build_context_with_images
    recent_msgs = _build_context_with_images(context_messages)
    messages = build_messages(recent_msgs, request.message, images=None)

    # --- Phase 3: Run orchestrator via queue ---

    queue: asyncio.Queue = asyncio.Queue()

    async def on_token(text):
        await queue.put({"event": "token", "data": json.dumps({"text": text})})

    async def on_card(card_data):
        logger.info("card_event_queued", extra={"card_type": card_data.get("type", "unknown")})
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
                images=request.images,
                lang=lang,
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

    # Background: profile extractor (LLM call runs parallel, DB write deferred)
    async def _run_profile_extractor_llm():
        """Extract profile-worthy info via LLM (no DB access)."""
        try:
            from app.agents.profile_extractor import extract_profile_info
            return await extract_profile_info(request.message, pets, lang=lang)
        except Exception as e:
            logger.warning("profile_extractor_bg_error", extra={"error": str(e)[:200]})
            return None

    extractor_task = asyncio.create_task(_run_profile_extractor_llm())

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

    # --- Layer 2: Post-processor guard ---
    # If LLM claimed action ("已更新/已记录") but didn't call any tools,
    # execute pre-analyzed actions deterministically as fallback.
    no_tools_called = not result.cards and not result.confirm_cards
    claims_action = response_claims_action(result.response_text)
    has_suggestions = bool(suggested_actions)

    if no_tools_called and claims_action and has_suggestions:
        logger.warning("post_processor_triggered", extra={
            "response_preview": result.response_text[:100],
            "suggested_count": len(suggested_actions),
        })

        async def on_card_fallback(card_data):
            logger.info("card_event_queued_fallback", extra={"card_type": card_data.get("type", "unknown")})
            yield_cards.append(card_data)

        yield_cards: list[dict] = []
        fallback_cards = await execute_suggested_actions(
            suggested_actions, db, user_id,
            on_card=None,
            location=request.location,
        )
        # Push fallback cards to SSE
        for card in fallback_cards:
            result.cards.append(card)
            yield {"event": "card", "data": json.dumps(card)}

    # Wait for profile extractor LLM call to finish, then write to DB
    try:
        extracted = await extractor_task
        if extracted:
            from app.agents.tools import execute_tool
            await execute_tool("update_pet_profile", extracted, db, user_id)
            await db.commit()
            logger.info("profile_extractor_saved", extra={
                "keys": list(extracted["info"].keys()),
            })
    except Exception as e:
        logger.warning("profile_extractor_save_error", extra={"error": str(e)[:200]})

    # Save assistant response
    all_cards = result.cards + result.confirm_cards
    cards_json = json.dumps(all_cards) if all_cards else None
    await _save_message(
        db, session.id, user_id, MessageRole.assistant,
        result.response_text, cards_json
    )

    # Trigger context compression if needed (async, non-blocking)
    # Must use a separate db session — the current one will be closed after response
    from app.database import async_session
    async def _summarize_bg():
        async with async_session() as bg_db:
            await trigger_summary_if_needed(session.id, bg_db, lang=lang)
    _track_task(_summarize_bg())

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
