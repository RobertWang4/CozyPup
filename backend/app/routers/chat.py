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
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

# --- Agent 模块导入 ---
from app.agents.emergency import build_emergency_hint, detect_emergency  # 紧急关键词检测 & 构建紧急提示
from app.agents.locale import detect_language                            # 语言检测（中/英）
from app.agents.orchestrator import run_orchestrator, OrchestratorResult  # 统一 Agent Loop
from app.agents.pending_actions import pop_action                        # 待确认动作的存取（用于 confirm-action）
from app.agents.post_processor import execute_suggested_actions           # 后处理：最终兜底执行
from app.agents.pre_processing import pre_process                        # 预处理：从用户消息中预分析可能的工具调用
from app.agents.prompts_v2 import build_messages, build_system_prompt    # 构建 system prompt 和消息列表
from app.agents.context_agent import trigger_summary_if_needed           # 上下文压缩：消息过多时自动摘要
from app.agents.trace_collector import TraceCollector, INACTIVE_TRACE    # Debug trace 收集器
from app.agents.tools import execute_tool                                # 工具执行器（用于 confirm-action 直接执行）
from app.auth import get_current_user_id                                 # JWT 认证依赖，提取 user_id
from app.config import settings                                          # 全局配置（模型名、API key 等）
from app.database import get_db                                          # 数据库会话依赖
from app.models import Chat, ChatSession, MessageRole, Pet               # SQLAlchemy 数据模型

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


class ConfirmActionRequest(BaseModel):
    """确认动作请求 — 用户点击卡片上的确认按钮时发送。"""
    action_id: str                         # 待确认动作的唯一 ID


async def _get_or_create_session(
    db: AsyncSession, user_id: uuid.UUID
) -> ChatSession:
    """获取或创建当日会话。

    设计决策：每个用户每天只有一个会话（daily session），
    这样可以在一天结束时对整天的对话做摘要压缩，节省 token。
    """
    today = date.today()
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.user_id == user_id,
            ChatSession.session_date == today,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        # 今天还没有会话，创建一个新的
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
    )
    db.add(msg)
    await db.commit()
    return msg


def _build_context_messages(context_messages: list[Chat]) -> list[dict]:
    """将数据库中的 Chat 对象转换为 LLM 需要的消息格式。

    注意：历史消息中的图片不会重新发送给 LLM（太贵了），
    只添加文字提示 "[附带了N张图片]" 让 LLM 知道用户之前发过图。
    """
    msgs = []
    for m in context_messages:
        content = m.content or ""
        if m.image_urls:
            n = len(m.image_urls)
            content += f"\n[附带了{n}张图片]"
        msgs.append({"role": m.role.value, "content": content})
    return msgs


# 哨兵对象，用于标记 SSE 流结束。用 object() 而不是 None，
# 因为 None 可能是合法的队列值，而 object() 实例是全局唯一的。
_SENTINEL = object()


async def _event_generator(
    request: ChatRequest, user_id: uuid.UUID, db: AsyncSession,
    trace: TraceCollector = INACTIVE_TRACE,
):
    """SSE 事件生成器 — 整个聊天流程的主函数。

    这是一个 async generator，每 yield 一个 dict 就会通过 SSE 推送给前端。
    整体流程分为 4 个阶段：
      Phase 1: 并行预处理（DB 查询 + 语言/紧急检测 + 图片保存）
      Phase 2: 构建 prompt（system prompt + 历史消息 + 当前消息）
      Phase 3: 调用 orchestrator 运行 LLM + 工具执行，流式输出
      Phase 4: 后处理（兜底执行、档案提取、消息保存、上下文压缩）
    """

    # ========== Phase 0: 会话 & 消息保存 ==========

    # 1. 获取或创建当日会话
    session = await _get_or_create_session(db, user_id)
    session_id = str(session.id)

    # 2. 立即保存用户消息（不等图片写入完成，优先让 LLM 开始处理）
    #    图片写入通过 run_in_executor 在线程池中并行进行
    image_save_task = None
    if request.images:
        loop = asyncio.get_event_loop()
        image_save_task = loop.run_in_executor(None, _save_images_to_disk, request.images)
    await _save_message(
        db, session.id, user_id, MessageRole.user, request.message,
    )

    from app.debug.trace_logger import trace_log
    trace_log("chat_request", data={
        "message": request.message,
        "image_urls": [img[:100] for img in (request.images or [])],
        "session_id": session_id,
    })

    # ========== Phase 1: 并行预处理 ==========

    # Stage 1: 顺序 DB 查询（同一个 AsyncSession 不支持并发操作）
    pets = await _get_pets(db, user_id)                   # 加载用户的所有宠物
    await db.refresh(session)                              # 确保 context_summary（摘要）字段已加载

    # Stage 2: 同步操作（纯 CPU，毫秒级，不需要 await）
    lang = request.language or detect_language(request.message)      # 检测语言（中/英）
    emergency_result = detect_emergency(request.message)              # 检测紧急关键词（如"中毒""抽搐"）
    suggested_actions = pre_process(request.message, pets, lang=lang) # 预分析：从文本中提取可能的工具调用

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

    # Stage 3: 加载最近的历史消息作为上下文
    context_messages = await _get_recent_messages(db, session.id, limit=MAX_CONTEXT_MESSAGES)

    # ========== Phase 2: 构建 Prompt ==========

    # 构建紧急提示（如果检测到紧急关键词，告诉 LLM 优先处理紧急情况）
    emergency_hint = (
        build_emergency_hint(emergency_result.keywords, lang=lang)
        if emergency_result.detected
        else None
    )

    # 构建预处理器提示 — 把预分析出的工具调用建议注入 prompt，
    # 引导 LLM 直接使用这些工具，减少 LLM 自己分析的负担
    preprocessor_hints = []
    for action in suggested_actions:
        if action.confidence >= 0.5:  # 只注入置信度 >= 50% 的建议
            preprocessor_hints.append(
                f"{action.tool_name}({json.dumps(action.arguments, ensure_ascii=False)})"
            )

    # 首次用户检测：无历史消息 + 无上下文摘要 = 新用户第一条消息
    is_first_message = not context_messages and not session.context_summary
    if is_first_message:
        first_hint = "introduce_product() — 这是新用户的第一条消息，先介绍产品功能" if lang == "zh" else "introduce_product() — This is a new user's first message, introduce product features first"
        preprocessor_hints.append(first_hint)

    # 多事件检测：如果用户一句话里提到了多个事件/提醒，
    # 提示 LLM 每个事件要单独调用一次工具（否则 LLM 容易只调一次）
    event_count = sum(1 for a in suggested_actions if a.tool_name == "create_calendar_event")
    reminder_count = sum(1 for a in suggested_actions if a.tool_name == "create_reminder")
    total_actions = event_count + reminder_count
    if total_actions >= 2:
        hint = "⚠️ 检测到多个事件/提醒意图，请确保每件事单独调用一次工具" if lang == "zh" else "⚠️ Multiple events/reminders detected — make a separate tool call for each"
        preprocessor_hints.append(hint)

    # 模型选择：紧急情况用更准确的模型（Kimi K2.5），日常用便宜的模型（Qwen3.5-Plus）
    is_emergency = emergency_result.detected
    model = settings.emergency_model if is_emergency else settings.model
    trace.record("model_selected", {"model": model, "is_emergency": is_emergency})

    # 构建 system prompt（按缓存友好的顺序组装各部分）
    today_str = date.today().isoformat()
    system_prompt = build_system_prompt(
        pets=pets,                                                      # 宠物档案信息
        session_summary=session.context_summary if session else None,   # 之前的对话摘要
        emergency_hint=emergency_hint,                                  # 紧急提示
        preprocessor_hints=preprocessor_hints if preprocessor_hints else None,  # 预分析建议
        today=today_str,                                                # 今天日期
        lang=lang,                                                      # 语言
    )
    trace.record("system_prompt", {"length": len(system_prompt), "content": system_prompt})

    # 等待图片保存完成（之前一直在后台线程并行运行）
    saved_image_urls = None
    if image_save_task is not None:
        saved_image_urls = await image_save_task
        # 异步回填图片 URL 到之前保存的用户消息
        _track_task(_backfill_image_urls(session.id, user_id, saved_image_urls))

    # 构建消息列表 — 图片不发给 LLM（太贵），只加文字提示
    # 图片会在 executor 层根据工具调用结果附加
    recent_msgs = _build_context_messages(context_messages)
    image_count = len(request.images) if request.images else 0
    messages = build_messages(recent_msgs, request.message, image_count=image_count)

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

    async def _run_orchestrator_to_queue():
        """在独立 Task 中运行 orchestrator，结果通过队列传递。

        orchestrator 内部流程：
        1. 调用 LLM（流式），同时通过 on_token 回调输出 token
        2. 如果 LLM 返回了 function call → 执行对应工具 → 通过 on_card 回调输出卡片
        3. 如果需要多轮工具调用，会循环执行（orchestrator loop）
        4. 最终返回 OrchestratorResult（包含完整回复文本和所有卡片）
        """
        try:
            result = await run_orchestrator(
                message=request.message,
                system_prompt=system_prompt,
                context_messages=messages,   # 历史消息 + 当前用户消息
                model=model,                 # 根据是否紧急选择的模型
                db=db,
                user_id=user_id,
                session_id=session.id,
                on_token=on_token,           # token 流式回调
                on_card=on_card,             # 卡片回调
                today=today_str,
                suggested_actions=suggested_actions,  # 预分析的工具调用（用于 nudge）
                location=request.location,   # 用户位置（用于附近搜索）
                images=request.images,       # 原始 base64 图片（用于图片分析工具）
                image_urls=saved_image_urls, # 已保存的图片 URL
                pets=pets,                   # 宠物列表（用于 confirm 描述）
                lang=lang,
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
    from app.agents.constants import NUDGE_TOOLS
    no_tools_called = not result.cards and not result.confirm_cards and not result.tools_called
    # Only fallback for critical tools (search_places, trigger_emergency, set_language)
    # Other pre-processor suggestions are advisory — trust the LLM's judgment
    critical_missed = any(
        a.confidence >= 0.8 and a.tool_name in NUDGE_TOOLS
        for a in suggested_actions
    )

    if no_tools_called and critical_missed:
        trace.record("post_processor_fallback", {
            "triggered": True,
            "suggested_count": len(suggested_actions),
        })
        logger.warning("final_fallback_triggered", extra={
            "response_preview": result.response_text[:100],
            "suggested_count": len(suggested_actions),
        })
        # Only execute critical tools in fallback, not all suggestions
        critical_actions = [a for a in suggested_actions if a.tool_name in NUDGE_TOOLS]
        fallback_cards = await execute_suggested_actions(
            critical_actions, db, user_id,
            on_card=None,
            location=request.location,
        )
        for card in fallback_cards:
            result.cards.append(card)
            yield {"event": "card", "data": json.dumps(card)}

    # 等待 profile extractor 的 LLM 调用完成，将提取的信息合并到宠物档案
    try:
        extracted = await extractor_task
        if extracted:
            from app.agents.profile_extractor import merge_into_profile_md
            # 找到目标宠物对象
            target_pet = next(
                (p for p in pets if str(p.id) == extracted["pet_id"]), None
            )
            if target_pet:
                # 将提取的信息（品种、年龄、体重等）合并到宠物的 profile_md
                new_md = await merge_into_profile_md(
                    target_pet, extracted["info"], lang=lang,
                )
                if new_md:
                    target_pet.profile_md = new_md
                    await db.commit()
                    logger.info("profile_extractor_saved", extra={
                        "keys": list(extracted["info"].keys()),
                        "md_length": len(new_md),
                    })
    except Exception as e:
        logger.warning("profile_extractor_save_error", extra={"error": str(e)[:200]})

    # --- RAG: 异步生成本轮对话的 embedding ---
    async def _write_embedding_bg():
        try:
            from app.rag.writer import write_chat_embedding
            from app.database import async_session as _async_session
            emb_content = f"用户: {request.message}\n助手: {result.response_text[:500]}"
            async with _async_session() as bg_db:
                await write_chat_embedding(
                    db=bg_db,
                    user_id=user_id,
                    source_id=session.id,
                    content=emb_content,
                )
        except Exception as e:
            logger.warning("embedding_bg_error", extra={"error": str(e)[:200]})
    _track_task(_write_embedding_bg())

    # 保存助手的完整回复到数据库（包含所有卡片的 JSON）
    all_cards = result.cards + result.confirm_cards
    cards_json = json.dumps(all_cards) if all_cards else None
    await _save_message(
        db, session.id, user_id, MessageRole.assistant,
        result.response_text, cards_json
    )

    # 触发上下文压缩（异步、非阻塞）
    # 当会话消息数超过阈值时，用 LLM 把旧消息压缩成摘要，存到 session.context_summary
    # 必须用独立的 DB session — 当前 session 在响应结束后会被关闭
    from app.database import async_session
    async def _summarize_bg():
        async with async_session() as bg_db:
            await trigger_summary_if_needed(session.id, bg_db, lang=lang)
    _track_task(_summarize_bg())

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
    """
    debug_on = raw_request.headers.get("X-Debug", "").lower() == "true"
    trace = TraceCollector(active=True) if debug_on else INACTIVE_TRACE
    return EventSourceResponse(_event_generator(request, user_id, db, trace=trace))


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
        result = await execute_tool(
            action.tool_name, action.arguments, db, user_id,
        )
        await db.commit()
    except Exception as exc:
        logger.error("confirm_action_error", extra={
            "action_id": str(action.id),
            "tool": action.tool_name,
            "error": str(exc)[:200],
        })
        raise HTTPException(status_code=500, detail=str(exc))

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
