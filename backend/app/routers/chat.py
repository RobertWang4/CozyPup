"""
Chat SSE 端点 — 将 LLM 响应以 Server-Sent Events (SSE) 流式传输给前端。

这是整个聊天功能的入口文件。iOS 客户端发送消息到 POST /api/v1/chat，
本模块负责：
1. 获取/创建当日会话（每天一个 session）
2. 保存用户消息到数据库
3. 并行执行预处理（语言检测、紧急检测、预分析动作）
4. 构建 system prompt 并调用 LLM（通过 orchestrator）
5. 将 LLM 的 token 流和 card 数据通过 SSE 推送给前端
6. 后处理：兜底执行、个人档案提取、上下文压缩
"""

import asyncio
import base64
import json
import logging
import time
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

# --- Agent 模块导入 ---
from app.agents.chat_turn import build_agent_prompt_input
from app.agents.chat_finalizer import (
    apply_profile_extraction,
    chat_turn_memory_source_id as _chat_turn_memory_source_id,
    finalize_assistant_turn,
    record_chat_audit,
    should_run_final_fallback,
)
from app.agents.emergency import detect_emergency                        # 紧急关键词检测
from app.agents.emergency_router import classify_emergency, render_for_user  # 紧急情况短路路由（跳过 memory + LLM）
from app.agents.engine import AgentEngine, AgentRunInput
from app.agents.locale import detect_language                            # 语言检测（中/英）
from app.agents.orchestrator import OrchestratorResult                   # 统一 Agent Loop
from app.agents.pending_actions import pop_action                        # 待确认动作的存取（用于 confirm-action）
from app.agents.post_processor import execute_suggested_actions           # 后处理：最终兜底执行
from app.agents.pre_processing import pre_process                        # 预处理：从用户消息中预分析可能的工具调用
from app.agents.trace_collector import TraceCollector, INACTIVE_TRACE    # Debug trace 收集器
from app.agents.tools import execute_tool                                # 工具执行器（用于 confirm-action 直接执行）
from app.auth import get_current_user_id                                 # JWT 认证依赖，提取 user_id
from app.debug.correlation import get_correlation_id                      # 当前请求的 correlation ID
from app.middleware.subscription import require_active_subscription, billing_enabled  # 订阅状态检查
from app.database import get_db                                          # 数据库会话依赖
from app.models import Chat, ChatSession, MessageRole, Pet, User         # SQLAlchemy 数据模型
from datetime import datetime, timedelta, timezone                       # Used for trial expiry check

# 7-day trial window — mirrors app.routers.subscription.TRIAL_DAYS
_CHAT_TRIAL_DAYS = 7

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chat"])

# 上下文窗口内最多携带的历史消息数量（太多会浪费 token，太少会丢失上下文）
MAX_CONTEXT_MESSAGES = 5

# 图片保存目录：Docker 环境用 /app/uploads，本地开发用项目内的 uploads 目录
PHOTO_DIR = Path("/app/uploads/photos") if Path("/app/uploads").exists() else Path(__file__).resolve().parent.parent / "uploads" / "photos"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)


# 后台任务追踪集合 — 防止 fire-and-forget 的协程被垃圾回收
# Python 的 asyncio.create_task 返回的 Task 如果没有引用，可能会被 GC 掉
_bg_tasks: set[asyncio.Task] = set()


def _track_task(coro):
    """创建一个被追踪的后台任务，确保它不会被垃圾回收。"""
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)                    # 加入集合保持引用
    task.add_done_callback(_bg_tasks.discard)  # 完成后自动移除


class ChatRequest(BaseModel):
    """聊天请求体 — iOS 客户端发送的 JSON 结构。"""
    message: str                           # 用户输入的文本消息
    session_id: str | None = None          # 会话 ID（目前未使用，服务端按日期自动管理）
    location: dict | None = None           # 用户位置 {"lat": float, "lng": float}，用于附近搜索
    language: str | None = None            # 语言偏好 "zh"/"en"，None 时自动检测
    images: list[str] | None = None        # base64 编码的 JPEG 图片列表
    new_session: bool = False              # True 时强制开新会话（iOS /clear 后置位一次）


class ConfirmActionRequest(BaseModel):
    """确认动作请求 — 用户点击卡片上的确认按钮时发送。"""
    action_id: str                         # 待确认动作的唯一 ID


def _user_today(tz_name: str | None, now: datetime | None = None) -> date:
    """Today's date in the user's timezone (IANA name from X-Timezone header).

    The server runs in UTC; a user in the Americas chatting in the evening is
    still on "yesterday" by their clock. Falls back to UTC when the header is
    missing or invalid.
    """
    from zoneinfo import ZoneInfo

    current = now or datetime.now(timezone.utc)
    if tz_name:
        try:
            return current.astimezone(ZoneInfo(tz_name)).date()
        except Exception:
            pass
    return current.astimezone(timezone.utc).date()


async def _get_or_create_session(
    db: AsyncSession, user_id: uuid.UUID, force_new: bool = False,
    today: date | None = None,
) -> ChatSession:
    """获取或创建当日会话。

    默认：每个用户每天一个会话，取今天最新的一条（按 created_at DESC）。
    force_new=True：强制新建一条今天的会话（iOS 用户 /clear 后的第一条消息会传这个），
      这样 _load_recent_messages 和 context_summary 都是空的，上下文从零开始。
    """
    today = today or date.today()
    if not force_new:
        result = await db.execute(
            select(ChatSession)
            .where(
                ChatSession.user_id == user_id,
                ChatSession.session_date == today,
            )
            .order_by(ChatSession.created_at.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()
        if session is not None:
            return session
    session = ChatSession(
        id=uuid.uuid4(), user_id=user_id, session_date=today
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def _get_pets(db: AsyncSession, user_id: uuid.UUID) -> list[Pet]:
    """加载用户的所有宠物档案，用于注入 system prompt 让 LLM 了解宠物信息。"""
    result = await db.execute(
        select(Pet).where(Pet.user_id == user_id).order_by(Pet.created_at)
    )
    return list(result.scalars().all())


async def _get_recent_messages(
    db: AsyncSession, session_id: uuid.UUID, limit: int = 5
) -> list[Chat]:
    """加载会话中最近的消息作为上下文。

    按时间倒序取 limit 条，再反转回正序，这样 LLM 看到的是时间正序的对话。
    只取未被摘要压缩的消息（已压缩的在 session.context_summary 中）。
    """
    result = await db.execute(
        select(Chat)
        .where(Chat.session_id == session_id)
        .order_by(Chat.created_at.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


def _save_images_to_disk(images_b64: list[str]) -> list[str]:
    """将 base64 编码的图片保存到磁盘，返回 URL 路径列表。

    这是一个同步函数，通过 run_in_executor 在线程池中运行，
    这样磁盘 IO 不会阻塞主事件循环，可以和 DB 查询、LLM 调用并行。
    """
    urls = []
    for img_b64 in images_b64:
        try:
            image_data = base64.b64decode(img_b64)
            if len(image_data) > 5 * 1024 * 1024:  # 跳过超过 5MB 的图片
                continue
            photo_id = uuid.uuid4()
            filename = f"{photo_id}.jpg"
            (PHOTO_DIR / filename).write_bytes(image_data)
            urls.append(f"/api/v1/calendar/photos/{filename}")
        except Exception:
            continue  # 单张图片解码失败不影响其他图片
    return urls


async def _backfill_image_urls(
    session_id: uuid.UUID, user_id: uuid.UUID, image_urls: list[str]
):
    """回填图片 URL 到已保存的用户消息上。

    时序问题：用户消息需要先保存到 DB（这样 LLM 能尽快开始处理），
    但图片还在后台线程写入磁盘。写完后通过这个函数把 URL 补回去。
    使用独立的 DB session，因为原始 session 可能已经在做其他操作。
    """
    try:
        from app.database import async_session
        async with async_session() as db:
            result = await db.execute(
                select(Chat)
                .where(
                    Chat.session_id == session_id,
                    Chat.user_id == user_id,
                    Chat.role == MessageRole.user,
                )
                .order_by(Chat.created_at.desc())
                .limit(1)
            )
            msg = result.scalar_one_or_none()
            if msg:
                msg.image_urls = image_urls
                await db.commit()
    except Exception as e:
        logger.warning("backfill_image_urls_error", extra={"error": str(e)[:200]})


async def _save_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    role: MessageRole,
    content: str,
    cards_json: str | None = None,
    image_urls: list[str] | None = None,
) -> Chat:
    """保存一条消息到数据库（用户消息或助手回复）。

    cards_json: 卡片数据的 JSON 字符串（记录卡片、确认卡片等），
    用于 iOS 端重新加载历史消息时能还原卡片 UI。
    """
    msg = Chat(
        id=uuid.uuid4(),
        session_id=session_id,
        user_id=user_id,
        role=role,
        content=content,
        cards_json=cards_json,
        image_urls=image_urls,
        correlation_id=get_correlation_id() or None,
    )
    db.add(msg)
    await db.commit()
    return msg


# 哨兵对象，用于标记 SSE 流结束。用 object() 而不是 None，
# 因为 None 可能是合法的队列值，而 object() 实例是全局唯一的。
_SENTINEL = object()


def _months_since(d: date | None) -> int | None:
    """Return the number of whole months between d and today."""
    if d is None:
        return None
    today = date.today()
    return (today.year - d.year) * 12 + (today.month - d.month)


async def _load_recent_messages(db: AsyncSession, session_id: uuid.UUID, limit: int = 4) -> list[Chat]:
    """Load at most `limit` recent Chat rows for trace enrichment (time-ascending)."""
    rows = await db.execute(
        select(Chat).where(Chat.session_id == session_id).order_by(Chat.created_at.desc()).limit(limit)
    )
    return list(reversed(rows.scalars().all()))


async def _event_generator(
    request: ChatRequest, user_id: uuid.UUID, db: AsyncSession,
    trace: TraceCollector = INACTIVE_TRACE,
    client_version: str | None = None,
    tz_name: str | None = None,
):
    """SSE 事件生成器 — 整个聊天流程的主函数。

    这是一个 async generator，每 yield 一个 dict 就会通过 SSE 推送给前端。
    整体流程分为 4 个阶段：
      Phase 1: 并行预处理（DB 查询 + 语言/紧急检测 + 图片保存）
      Phase 2: 构建 prompt（system prompt + 历史消息 + 当前消息）
      Phase 3: 调用 orchestrator 运行 LLM + 工具执行，流式输出
      Phase 4: 后处理（兜底执行、档案提取、消息保存、上下文压缩）
    """

    # Audit timer — captures wall-clock response time for chat_audit_log.
    audit_start = time.monotonic()
    # Mutable flag set to True if the emergency router short-circuits
    # the memory path. Read in Phase 4 when writing the audit row.
    audit_is_emergency_route = False

    # ========== Phase 0: 会话初始化 ==========

    # 1. 获取或创建当日会话（"今天"按用户时区算，见 _user_today）
    user_today = _user_today(tz_name)
    session = await _get_or_create_session(
        db, user_id, force_new=bool(request.new_session), today=user_today,
    )
    session_id = str(session.id)

    # 2. 启动图片保存（在线程池中并行运行，不阻塞主流程）
    image_save_task = None
    if request.images:
        loop = asyncio.get_event_loop()
        image_save_task = loop.run_in_executor(None, _save_images_to_disk, request.images)

    # ========== Phase 1: 并行预处理 ==========

    # Stage 1: 顺序 DB 查询（同一个 AsyncSession 不支持并发操作）
    pets = await _get_pets(db, user_id)                   # 加载用户的所有宠物
    await db.refresh(session)                              # 确保 context_summary（摘要）字段已加载

    # --- 发送 chat_request trace（在 pets 加载后，以便捕获完整宠物快照）---
    from app.debug.trace_logger import trace_log

    _pet_snapshot = [
        {
            "id": str(p.id),
            "name": p.name,
            "species": getattr(p.species, "value", str(p.species)),
            "breed": p.breed or "",
            "age_months": _months_since(p.birthday) if p.birthday else None,
            "weight_kg": p.weight,
            "chronic_conditions": (p.profile or {}).get("chronic_conditions", []) if isinstance(p.profile, dict) else [],
        }
        for p in pets
    ]
    _tail = []
    _recent_for_trace = await _load_recent_messages(db, session.id, limit=4)
    for _m in _recent_for_trace:
        _tail.append({
            "role": _m.role.value if hasattr(_m.role, "value") else str(_m.role),
            "content_preview": (_m.content or "")[:200],
        })

    trace_log("chat_request", data={
        "message": request.message,
        "image_urls": [img[:100] for img in (request.images or [])],
        "image_urls_full": request.images or [],
        "session_id": session_id,
        "pet_snapshot": _pet_snapshot,
        "session_history_tail": _tail,
        "client_version": client_version,
    })

    # Stage 2: 同步操作（纯 CPU，毫秒级，不需要 await）
    lang = request.language or detect_language(request.message)      # 检测语言（中/英）
    emergency_result = detect_emergency(request.message)              # 检测紧急关键词（如"中毒""抽搐"）
    suggested_actions = pre_process(request.message, pets, today=user_today, lang=lang) # 预分析：从文本中提取可能的工具调用

    trace.record("language_detect", {"language": lang})
    trace.record("emergency_detect", {
        "detected": emergency_result.detected,
        "keywords": emergency_result.keywords if emergency_result.detected else [],
    })
    trace.record("pre_process", [
        {"tool": a.tool_name, "confidence": a.confidence, "args": a.arguments}
        for a in suggested_actions
    ])
    trace.record("pets", [{"id": str(p.id), "name": p.name} for p in pets])

    if emergency_result.detected:
        logger.info("emergency_keywords_detected", extra={
            "session_id": session_id,
            "user_id": str(user_id),
            "keywords": emergency_result.keywords,
        })

    # ========== Emergency short-circuit ==========
    # For UNAMBIGUOUS emergencies (toxin ingestion, seizure, urinary obstruction,
    # open-mouth-breathing cat, GDV, heatstroke, severe trauma, dystocia, collapse)
    # we bypass memory + LLM entirely and emit a structured emergency card. This:
    #   - removes LLM latency (~2-8s) on time-critical queries
    #   - removes the risk of the model producing unsafe free-form text
    #   - delivers a hotline number the owner can call immediately
    # The legal logic: we are NOT giving diagnosis or dosage — we are directing
    # the user to call a pet-poison hotline or go to an emergency vet.
    emergency_match = classify_emergency(request.message)
    if emergency_match is not None:
        audit_is_emergency_route = True
        trace.record("emergency_short_circuit", {
            "category": emergency_match.category,
            "keywords": emergency_match.keywords,
        })
        logger.info("emergency_short_circuit", extra={
            "session_id": session_id,
            "user_id": str(user_id),
            "category": emergency_match.category,
            "keywords": emergency_match.keywords,
        })

        # Persist the user message so session history stays consistent.
        await _save_message(
            db, session.id, user_id, MessageRole.user, request.message,
        )

        card = render_for_user(emergency_match, lang=lang)
        yield {"event": "card", "data": json.dumps(card, ensure_ascii=False)}
        # iOS also listens for event="emergency" per the docstring below; mirror it.
        yield {"event": "emergency", "data": json.dumps(card, ensure_ascii=False)}

        # Save a minimal assistant turn so history + audit have the emitted content.
        await _save_message(
            db, session.id, user_id, MessageRole.assistant,
            card["message"], json.dumps([card], ensure_ascii=False),
        )

        record_chat_audit(
            user_id=user_id,
            pets=pets,
            raw_query=request.message or "",
            is_emergency_route=True,
            all_cards=[],
            llm_output=card["message"],
            response_time_ms=int((time.monotonic() - audit_start) * 1000),
            model_used=None,
            session_id=session_id,
            lang=lang,
            tools_called=None,
            keyword_emergency=bool(emergency_result.detected),
            client_version=client_version,
            metadata_extra={
                "short_circuit": True,
                "category": emergency_match.category,
            },
        )

        yield {
            "event": "done",
            "data": json.dumps({"intent": "emergency", "session_id": session_id}),
        }
        return

    # Stage 3: 加载最近的历史消息作为上下文（必须在保存用户消息之前，避免重复）
    context_messages = await _get_recent_messages(db, session.id, limit=MAX_CONTEXT_MESSAGES)

    # Stage 4: 保存用户消息到 DB（在查询 context 之后，避免当前消息出现在历史中导致重复）
    await _save_message(
        db, session.id, user_id, MessageRole.user, request.message,
    )

    # ========== Phase 2: 构建 Prompt ==========

    image_count = len(request.images) if request.images else 0
    prompt_input = await build_agent_prompt_input(
        message=request.message,
        db=db,
        user_id=user_id,
        pets=pets,
        session_summary=session.context_summary if session else None,
        context_messages=context_messages,
        emergency_result=emergency_result,
        suggested_actions=suggested_actions,
        lang=lang,
        image_count=image_count,
        today=user_today.isoformat(),
    )
    model = prompt_input.model
    today_str = prompt_input.today
    system_prompt = prompt_input.system_prompt
    messages = prompt_input.messages
    recent_image_urls = prompt_input.recent_image_urls
    trace.record("model_selected", {"model": model, "is_emergency": emergency_result.detected})
    trace.record("system_prompt", {"length": len(system_prompt), "content": system_prompt})

    # 等待图片保存完成（之前一直在后台线程并行运行）
    saved_image_urls = None
    if image_save_task is not None:
        saved_image_urls = await image_save_task
        # 异步回填图片 URL 到之前保存的用户消息
        _track_task(_backfill_image_urls(session.id, user_id, saved_image_urls))

    # ========== Phase 3: 运行 Orchestrator（核心 LLM 调用 + 工具执行） ==========

    # 使用 asyncio.Queue 将 orchestrator 的输出（token、card）桥接到 SSE generator。
    # 这样 orchestrator 可以在一个独立的 Task 中运行，产生的事件通过队列传递给 SSE 流。
    queue: asyncio.Queue = asyncio.Queue()

    async def on_token(text):
        """LLM 每生成一个 token 就调用这个回调，推入队列。"""
        await queue.put({"event": "token", "data": json.dumps({"text": text})})

    async def on_card(card_data):
        """工具执行完成后生成的卡片（记录卡片、地图卡片等）推入队列。"""
        card_type = card_data.get("type", "unknown")
        logger.info("card_event_queued", extra={"card_type": card_type})
        # 紧急卡片用专门的 SSE event type，iOS 端会特殊处理（红色横幅 + 紧急电话）
        sse_event = "emergency" if card_type == "emergency" else "card"
        await queue.put({"event": sse_event, "data": json.dumps(card_data)})

    async def on_thinking(text: str, tool_name: str):
        """Server-generated status string, shown as gray italic bubble on iOS.
        Fired the moment the LLM's tool name is identified in the stream, so
        the user sees activity without the LLM emitting opener text (which
        caused decoder-drift fabrication on grok-4-1-fast)."""
        await queue.put({
            "event": "thinking",
            "data": json.dumps({"text": text, "tool": tool_name}, ensure_ascii=False),
        })

    async def _run_orchestrator_to_queue():
        """在独立 Task 中运行 orchestrator，结果通过队列传递。

        orchestrator 内部流程：
        1. 调用 LLM（流式），同时通过 on_token 回调输出 token
        2. 如果 LLM 返回了 function call → 执行对应工具 → 通过 on_card 回调输出卡片
        3. 如果需要多轮工具调用，会循环执行（orchestrator loop）
        4. 最终返回 OrchestratorResult（包含完整回复文本和所有卡片）
        """
        try:
            result = await AgentEngine().run(
                AgentRunInput(
                    message=request.message,
                    messages=messages,        # 历史消息 + 当前用户消息
                    system_prompt=system_prompt,
                    model=model,              # 根据是否紧急选择的模型
                    db=db,
                    user_id=user_id,
                    session_id=session.id,
                    location=request.location,
                    language=lang,
                    image_urls=saved_image_urls or [],
                ),
                on_token=on_token,           # token 流式回调
                on_card=on_card,             # 卡片回调
                on_thinking=on_thinking,     # 思考气泡（工具名字幕）
                today=today_str,
                suggested_actions=suggested_actions,  # 预分析的工具调用（用于 nudge）
                images=request.images,       # 原始 base64 图片（用于图片分析工具）
                recent_image_urls=recent_image_urls,  # 历史消息中的图片 URL（回退用）
                pets=pets,                   # 宠物列表（用于 confirm 描述）
                trace=trace,                 # Debug trace 收集器
            )
            await queue.put(("_result", result))  # 用元组包装结果，和普通 SSE 事件区分
        except Exception as e:
            # orchestrator 异常时，给用户返回错误消息而不是让 SSE 流断开
            logger.error("orchestrator_error", extra={
                "error_type": type(e).__name__,
                "error_message": str(e)[:500],
            })
            error_text = f"Sorry, I'm having trouble right now. Please try again. (Error: {type(e).__name__})"
            await queue.put({"event": "token", "data": json.dumps({"text": error_text})})
            await queue.put(("_result", OrchestratorResult(response_text=error_text)))
        finally:
            await queue.put(_SENTINEL)  # 发送哨兵信号，通知消费循环结束

    # 启动 orchestrator Task（在后台运行，不阻塞 generator）
    task = asyncio.create_task(_run_orchestrator_to_queue())

    # 并行启动 profile extractor：用另一个 LLM 调用从用户消息中提取宠物档案信息
    # 这个调用和主 orchestrator 完全并行，不影响响应速度
    async def _run_profile_extractor_llm():
        """从用户消息中提取宠物档案相关信息（品种、年龄、体重等）。

        使用独立的 LLM 调用，和主聊天 LLM 并行运行。
        只做提取，不写 DB — DB 写入在 Phase 4 中完成。
        """
        try:
            from app.agents.profile_extractor import extract_profile_info
            return await extract_profile_info(request.message, pets, lang=lang)
        except Exception as e:
            logger.warning("profile_extractor_bg_error", extra={"error": str(e)[:200]})
            return None

    extractor_task = asyncio.create_task(_run_profile_extractor_llm())

    # 消费队列：从队列中取出事件，yield 给 SSE 流
    # 遇到 _SENTINEL 时退出循环，遇到 _result 元组时保存结果
    result = None
    while True:
        item = await queue.get()
        if item is _SENTINEL:
            break                          # orchestrator 完成，退出循环
        if isinstance(item, tuple) and item[0] == "_result":
            result = item[1]               # 保存 OrchestratorResult，不 yield
            continue
        yield item                         # yield SSE 事件给前端

    await task  # 确保 Task 完全结束（异常也会在这里抛出）

    # ========== Phase 4: 后处理 ==========

    if result is None:
        result = OrchestratorResult()

    # --- 最终兜底层 ---
    # Nudge 机制（在 orchestrator 内部）已处理大部分"LLM 不调工具"的情况。
    # 这里只处理 nudge 也失败后的最终兜底：如果仍然没有工具被调用，
    # 但预处理有高置信度建议，直接确定性执行。
    if should_run_final_fallback(result, suggested_actions):
        trace.record("post_processor_fallback", {
            "triggered": True,
            "suggested_count": len(suggested_actions),
        })
        logger.warning("final_fallback_triggered", extra={
            "response_preview": result.response_text[:100],
            "suggested_count": len(suggested_actions),
        })
        # Only execute critical tools in fallback, not all suggestions
        from app.agents.constants import NUDGE_TOOLS
        critical_actions = [a for a in suggested_actions if a.tool_name in NUDGE_TOOLS]
        fallback_cards = await execute_suggested_actions(
            critical_actions, db, user_id,
            on_card=None,
            location=request.location,
        )
        for card in fallback_cards:
            result.cards.append(card)
            yield {"event": "card", "data": json.dumps(card)}

    await apply_profile_extraction(
        extractor_task=extractor_task,
        pets=pets,
        db=db,
        lang=lang,
    )

    finalization = await finalize_assistant_turn(
        db=db,
        session_id=session.id,
        user_id=user_id,
        assistant_role=MessageRole.assistant,
        result=result,
        user_message=request.message,
        lang=lang,
        save_message=_save_message,
        track_task=_track_task,
    )
    all_cards = finalization.all_cards

    # 发送 debug trace（仅在 X-Debug: true 时）
    if trace.active:
        trace.record("orchestrator_result", {
            "response_text_length": len(result.response_text),
            "cards_count": len(result.cards),
            "confirm_cards_count": len(result.confirm_cards),
            "tools_called": list(result.tools_called),
        })
        yield {
            "event": "__debug__",
            "data": json.dumps(trace.to_dict(), ensure_ascii=False, default=str),
        }

    trace_log("chat_response", data={
        "final_text": result.response_text[:500] if result.response_text else "",
        "cards": [c.get("type", "unknown") for c in all_cards] if all_cards else [],
        "tools_called": list(result.tools_called),
        "total_prompt_tokens": getattr(result, "total_prompt_tokens", None),
        "total_completion_tokens": getattr(result, "total_completion_tokens", None),
        "model": getattr(result, "model_used", ""),
    })

    record_chat_audit(
        user_id=user_id,
        pets=pets,
        raw_query=request.message or "",
        is_emergency_route=audit_is_emergency_route,
        all_cards=all_cards,
        llm_output=result.response_text or None,
        response_time_ms=int((time.monotonic() - audit_start) * 1000),
        model_used=getattr(result, "model_used", None) or model,
        session_id=session_id,
        lang=lang,
        tools_called=result.tools_called,
        keyword_emergency=bool(emergency_result.detected),
        client_version=client_version,
    )

    # 发送 done 事件 — iOS 端收到后停止 loading 动画，标记流结束
    yield {
        "event": "done",
        "data": json.dumps({"intent": "chat", "session_id": session_id}),
    }


@router.post("/chat")
async def chat(
    request: ChatRequest,
    raw_request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """主聊天端点 — 接收用户消息，返回 SSE 流。

    iOS 端通过 ChatService.swift 调用此端点，使用 SSE 接收流式响应。
    SSE 事件类型：
    - event: token   → LLM 生成的文本片段（前端逐字显示）
    - event: card    → 工具执行结果卡片（记录卡片、地图卡片等）
    - event: emergency → 紧急情况卡片（红色横幅 + 紧急联系方式）
    - event: __debug__ → Debug trace（仅在 X-Debug: true 时）
    - event: done    → 流结束信号（前端停止 loading）

    订阅门禁：付费用户（trial 内 / active）走完整 LLM 流程；过期用户收到
    固定的升级提示流（几条 token + 一张 upgrade_prompt 卡片 + done），
    不调用 LLM，也不扣 rate limit 配额以外的任何资源。
    """
    # --- Subscription gate (only blocks /chat — other endpoints remain free) ---
    user_q = await db.execute(select(User).where(User.id == user_id))
    user = user_q.scalar_one_or_none()
    if billing_enabled() and user is not None and _is_subscription_expired(user):
        await db.commit()  # persist any status flip from trial→expired
        lang = (request.language or "zh").lower()
        return EventSourceResponse(_upgrade_prompt_generator(lang))

    debug_on = raw_request.headers.get("X-Debug", "").lower() == "true"
    trace = TraceCollector(active=True) if debug_on else INACTIVE_TRACE
    client_version = raw_request.headers.get("X-Client-Version")
    tz_name = raw_request.headers.get("X-Timezone")
    return EventSourceResponse(_event_generator(
        request, user_id, db, trace=trace, client_version=client_version, tz_name=tz_name,
    ))


def _is_subscription_expired(user: User) -> bool:
    """Return True if the user's subscription is expired; flip status in-memory if needed.

    Called by POST /chat as the only enforcement point. Other endpoints remain
    usable even when expired (per the "chat is the only locked feature" product
    decision).
    """
    if user.subscription_status == "expired":
        return True

    if user.subscription_status == "trial" and user.trial_start_date:
        elapsed = datetime.now(timezone.utc) - user.trial_start_date
        if elapsed > timedelta(days=_CHAT_TRIAL_DAYS):
            user.subscription_status = "expired"
            return True

    if user.subscription_status == "active" and user.subscription_expires_at:
        if datetime.now(timezone.utc) > user.subscription_expires_at:
            user.subscription_status = "expired"
            return True

    return False


async def _upgrade_prompt_generator(lang: str):
    """Canned SSE stream shown to expired users instead of calling the LLM.

    Emits a short assistant message and an `upgrade_prompt` card that the
    iOS client renders as a tappable card opening the paywall.
    """
    if lang == "en":
        lines = [
            "Your free trial has ended, so I can't chat for now. ",
            "You can still edit pet profiles, calendar events, reminders, and view your history for free — ",
            "but live AI conversations require a subscription. Tap below to upgrade and I'll be right here. 🐾",
        ]
    else:
        lines = [
            "你的免费试用已经结束，我暂时没办法继续和你对话了。",
            "宠物档案、日历、提醒和历史记录依然可以免费编辑和查看，",
            "但跟 AI 的实时对话需要订阅。点下面的升级按钮，我就回来继续陪你。🐾",
        ]

    for text in lines:
        yield {"event": "token", "data": json.dumps({"text": text})}
        await asyncio.sleep(0.02)  # small pause so the client renders progressively

    yield {
        "event": "card",
        "data": json.dumps({
            "type": "upgrade_prompt",
            "reason": "subscription_expired",
        }),
    }

    yield {
        "event": "done",
        "data": json.dumps({"intent": "upgrade_prompt", "session_id": ""}),
    }


@router.post("/chat/confirm-action")
async def confirm_action(
    request: ConfirmActionRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """确认动作端点 — 用户点击卡片上的确认按钮时触发。

    使用场景：LLM 返回了一个需要用户确认的动作（如删除宠物、修改记录），
    前端显示 ConfirmActionCard，用户点击"确认"后调用此端点。

    关键设计：不涉及 LLM — 直接从数据库中取出预存的工具名和参数，执行即可。
    这样既快速又确定性，不会出现 LLM 二次理解偏差。
    """
    # 从 pending_actions 表中取出并删除该动作（pop 语义，防止重复执行）
    action = await pop_action(db, request.action_id, str(user_id))
    if not action:
        raise HTTPException(status_code=404, detail="Action not found or expired")

    try:
        # 直接执行工具（绕过 LLM，使用预存的参数）
        # User already tapped confirm — force-lock any lockable fields so
        # update_pet_profile doesn't loop back into another confirm card.
        args = dict(action.arguments)
        if action.tool_name == "update_pet_profile":
            args.setdefault("_force_lock", True)
        result = await execute_tool(
            action.tool_name, args, db, user_id,
        )
        await db.commit()
    except Exception as exc:
        logger.error("confirm_action_error", extra={
            "action_id": str(action.id),
            "tool": action.tool_name,
            "error": str(exc)[:200],
        })
        raise HTTPException(status_code=500, detail=str(exc))

    # 防御：确认后工具不应再返回 needs_confirm — 出现就是 bug（例如忘了注入
    # _force_lock 导致 update_pet_profile 又回到确认分支）。打错误日志而不是
    # 静默返回"成功"欺骗前端。
    if result.get("needs_confirm"):
        logger.error("confirm_action_reentrant_needs_confirm", extra={
            "action_id": str(action.id),
            "tool": action.tool_name,
            "arguments_keys": list(action.arguments.keys()),
        })
        raise HTTPException(
            status_code=500,
            detail="Tool returned needs_confirm after confirmation — pipeline bug",
        )

    # 将确认执行的结果保存为助手消息（这样用户回看历史时能看到）
    session_id = action.session_id
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
