"""
Unified Agent Loop — 统一的 orchestrator，替代旧的 4 路径架构。

核心设计：一个 while 循环处理所有场景（纯聊天、单工具、多工具、图片）。
加入 nudge 机制：当 LLM 没调用预期的工具时，催促它重试一轮。

流程：
  1. 流式调 LLM
  2. 如果有 tool_calls → 逐个 dispatch → 把结果喂回 → 继续循环
  3. 如果没有 tool_calls → 检查 nudge → 退出或重试
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Callable, Awaitable

import litellm

from app.agents import llm_extra_kwargs
from app.agents.constants import CONFIRM_TOOLS, maybe_await
from app.agents.locale import t
from app.agents.micro_compact import micro_compact
from app.agents.pending_actions import store_action
from app.agents.pre_processing.types import SuggestedAction
from app.agents.tools import execute_tool, get_tool_definitions
from app.agents.trace_collector import TraceCollector, INACTIVE_TRACE
from app.agents.validation import validate_tool_args
from app.config import settings

logger = logging.getLogger(__name__)

MAX_ROUNDS = 5            # 最多循环轮次（含 nudge 重试）
NUDGE_CONFIDENCE = 0.8    # nudge 触发的最低置信度


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class OrchestratorResult:
    """orchestrator 执行结果。"""
    response_text: str = ""
    cards: list[dict] = field(default_factory=list)
    confirm_cards: list[dict] = field(default_factory=list)
    tools_called: set[str] = field(default_factory=set)
    plan_steps: list[dict] = field(default_factory=list)  # Steps from plan() tool


# ---------------------------------------------------------------------------
# _describe_tool_call — 生成工具调用的人类可读描述（用于 confirm card）
# ---------------------------------------------------------------------------

def _describe_tool_call(fn_name: str, fn_args: dict, pets: list | None = None, lang: str = "zh") -> str:
    """Generate human-readable description from LLM's tool call arguments."""
    def _pet_name(pid: str) -> str:
        if not pets:
            return ""
        for p in pets:
            if str(p.id if hasattr(p, "id") else p.get("id", "")) == pid:
                return p.name if hasattr(p, "name") else p.get("name", "")
        return ""

    pid = fn_args.get("pet_id", "")
    name = _pet_name(pid)
    label = f"「{name}」" if name else ""

    if fn_name == "update_pet_profile":
        info = fn_args.get("info", {})
        if "name" in info:
            return t("desc_rename", lang).format(label=label, name=info['name'])
        keys = ", ".join(info.keys())
        return t("desc_update_pet", lang).format(label=label, keys=keys)
    if fn_name == "create_pet":
        return t("desc_create_pet", lang).format(name=fn_args.get('name', ''))
    if fn_name == "delete_pet":
        return t("desc_delete_pet", lang).format(label=label)
    if fn_name == "create_calendar_event":
        title = fn_args.get("title", "")
        d = fn_args.get("event_date", "")
        return t("desc_create_event", lang).format(title=title, date=d)
    if fn_name == "update_calendar_event":
        return t("desc_update_event", lang)
    if fn_name == "delete_calendar_event":
        return t("desc_delete_event", lang)
    if fn_name == "create_reminder":
        return t("desc_create_reminder", lang).format(title=fn_args.get('title', ''))
    if fn_name == "update_reminder":
        return t("desc_update_reminder", lang)
    if fn_name == "delete_reminder":
        return t("desc_delete_reminder", lang)
    if fn_name == "delete_all_reminders":
        return t("desc_delete_all_reminders", lang)
    if fn_name == "draft_email":
        return t("desc_draft_email", lang).format(subject=fn_args.get('subject', ''))
    if fn_name == "save_pet_profile_md":
        return t("desc_save_profile", lang).format(label=label)
    if fn_name == "set_pet_avatar":
        return t("desc_set_avatar", lang).format(label=label)
    if fn_name == "upload_event_photo":
        return t("desc_upload_photo", lang)
    return fn_name


# ---------------------------------------------------------------------------
# dispatch_tool — 统一的工具分发：validate → confirm → execute → card
# ---------------------------------------------------------------------------

async def dispatch_tool(
    tool_call: dict,
    db,
    user_id,
    session_id,
    result: OrchestratorResult,
    on_card: Callable | None,
    lang: str,
    pets: list | None = None,
    images: list[str] | None = None,
    image_urls: list[str] | None = None,
    **kwargs,
) -> dict:
    """统一的工具执行入口。

    始终返回一个 dict（不会返回 None 或抛异常到调用方）。
    - 验证失败 → {"error": "..."}（LLM 下一轮会看到错误并自动修正）
    - confirm 门控 → {"status": "waiting_confirm", "message": "..."}
    - 正常执行 → 工具返回的结果 dict
    """
    fn_name = tool_call["function"]["name"]

    try:
        fn_args = json.loads(tool_call["function"]["arguments"])
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid JSON arguments: {exc}"}

    result.tools_called.add(fn_name)

    # --- create_calendar_event: 拦截未提到的宠物 ---
    if fn_name == "create_calendar_event" and fn_args.get("pet_id") and pets:
        user_msgs = [m.get("content", "") for m in kwargs.get("_messages", []) if m.get("role") == "user" and isinstance(m.get("content"), str)]
        last_user = user_msgs[-1] if user_msgs else ""
        # Find which pets are mentioned by name
        mentioned_pet_ids = set()
        for p in pets:
            pname = p.name if hasattr(p, "name") else p.get("name", "")
            pid = str(p.id if hasattr(p, "id") else p.get("id", ""))
            if pname and pname.lower() in last_user.lower():
                mentioned_pet_ids.add(pid)
        # If user mentioned specific pet(s) but this call is for an unmentioned pet, block it
        if mentioned_pet_ids and fn_args["pet_id"] not in mentioned_pet_ids:
            blocked_name = ""
            for p in pets:
                pid = str(p.id if hasattr(p, "id") else p.get("id", ""))
                if pid == fn_args["pet_id"]:
                    blocked_name = p.name if hasattr(p, "name") else p.get("name", "")
            logger.info("pet_mismatch_blocked", extra={
                "blocked_pet": blocked_name,
                "mentioned": list(mentioned_pet_ids),
                "user_text": last_user[:60],
            })
            return {"success": False, "error": f"用户只提到了特定的宠物，没有提到{blocked_name}。请只为用户提到的宠物创建事件。"}

    # --- create_calendar_event: 自动补全 cost ---
    if fn_name == "create_calendar_event" and fn_args.get("cost") is None:
        import re
        user_msgs = [m.get("content", "") for m in kwargs.get("_messages", []) if m.get("role") == "user" and isinstance(m.get("content"), str)]
        last_user = user_msgs[-1] if user_msgs else ""
        # Match: 花了300/花了300块/花了100/300元/cost 50
        cost_match = re.search(r"花了?\s*(\d+(?:\.\d+)?)\s*[块元刀]?|(\d+(?:\.\d+)?)\s*[块元刀]", last_user)
        if cost_match:
            amount = float(cost_match.group(1) or cost_match.group(2))
            fn_args["cost"] = amount
            tool_call["function"]["arguments"] = json.dumps(fn_args, ensure_ascii=False)
            logger.info("cost_auto_fixed", extra={"extracted": amount, "user_text": last_user[:60]})

    # --- create_daily_task: 自动补全 end_date ---
    if fn_name == "create_daily_task" and not fn_args.get("end_date"):
        import re
        from datetime import date as _date, timedelta as _td
        user_msgs = [m.get("content", "") for m in kwargs.get("_messages", []) if m.get("role") == "user" and isinstance(m.get("content"), str)]
        last_user = user_msgs[-1] if user_msgs else ""
        today = _date.today()
        extracted_end = None

        # "到4月10号" / "到4月10日"
        m = re.search(r"到(\d{1,2})月(\d{1,2})[号日]", last_user)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            year = today.year if month >= today.month else today.year + 1
            try:
                extracted_end = _date(year, month, day)
            except ValueError:
                pass

        # "到下周日" / "到下周六" etc
        if not extracted_end:
            m = re.search(r"到?下周([一二三四五六日天])", last_user)
            if m:
                weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
                target_wd = weekday_map.get(m.group(1), 6)
                days_ahead = (target_wd - today.weekday()) % 7 + 7  # next week
                extracted_end = today + _td(days=days_ahead)

        # "接下来7天" / "接下来N天"
        if not extracted_end:
            m = re.search(r"接下来(\d+)天", last_user)
            if m:
                extracted_end = today + _td(days=int(m.group(1)))

        # "这周" / "本周"
        if not extracted_end and re.search(r"[这本]周", last_user):
            days_to_sunday = 6 - today.weekday()
            extracted_end = today + _td(days=max(days_to_sunday, 1))

        if extracted_end:
            fn_args["end_date"] = extracted_end.isoformat()
            # Rewrite the tool_call arguments so execute_tool sees the fix
            tool_call["function"]["arguments"] = json.dumps(fn_args, ensure_ascii=False)
            logger.info("end_date_auto_fixed", extra={
                "extracted": extracted_end.isoformat(),
                "user_text": last_user[:60],
            })

    # --- plan：多步骤规划，不走 DB ---
    if fn_name == "plan":
        steps = fn_args.get("steps", [])
        result.plan_steps = steps
        step_summary = "; ".join(f"[{s.get('id')}] {s.get('action')}" for s in steps)
        return {
            "status": "planned",
            "message": f"已规划 {len(steps)} 个步骤: {step_summary}",
            "steps": steps,
        }

    # --- request_images：返回特殊标记，主循环会注入图片 ---
    if fn_name == "request_images":
        if not images:
            return {"error": "用户没有附带图片" if lang == "zh" else "No images attached"}
        return {
            "status": "images_loaded",
            "message": "图片已加载" if lang == "zh" else "Images loaded",
            "_inject_images": images,
        }

    # --- Confirm gate：破坏性工具需要用户确认 ---
    if fn_name in CONFIRM_TOOLS and session_id:
        desc = _describe_tool_call(fn_name, fn_args, pets=pets, lang=lang)
        action_id = await store_action(
            db=db, user_id=str(user_id), session_id=str(session_id),
            tool_name=fn_name, arguments=fn_args, description=desc,
        )
        card = {"type": "confirm_action", "action_id": action_id, "message": desc}
        result.confirm_cards.append(card)
        if on_card:
            await maybe_await(on_card, card)
        return {"status": "waiting_confirm", "message": desc}

    # --- Validate ---
    errors = validate_tool_args(fn_name, fn_args)
    if errors:
        return {"error": "; ".join(errors)}

    # --- Execute ---
    try:
        # 透传 image_urls 和 location 给所有工具，工具侧自行决定是否使用
        exec_kwargs = {}
        if "location" in kwargs:
            exec_kwargs["location"] = kwargs["location"]
        if image_urls:
            exec_kwargs["image_urls"] = image_urls

        tool_result = await execute_tool(fn_name, fn_args, db, user_id, **exec_kwargs)
        await db.commit()
    except Exception as exc:
        logger.error("dispatch_tool_error", extra={
            "tool": fn_name, "error": str(exc)[:300],
        })
        return {"error": str(exc)[:200]}

    # --- Handle needs_confirm（部分工具执行后仍需确认） ---
    if tool_result.get("needs_confirm") and session_id:
        confirm_tool = tool_result.get("confirm_tool", fn_name)
        confirm_args = tool_result.get("confirm_arguments", fn_args)
        confirm_desc = tool_result.get("confirm_description", f"确认执行 {fn_name}")
        action_id = await store_action(
            db=db, user_id=str(user_id), session_id=str(session_id),
            tool_name=confirm_tool, arguments=confirm_args, description=confirm_desc,
        )
        card = {"type": "confirm_action", "action_id": action_id, "message": confirm_desc}
        result.confirm_cards.append(card)
        if on_card:
            await maybe_await(on_card, card)
        return tool_result

    # --- Emit card ---
    card = tool_result.get("card")
    if card:
        result.cards.append(card)
        if on_card:
            await maybe_await(on_card, card)

    return tool_result


# ---------------------------------------------------------------------------
# Nudge helpers — 催促 LLM 调用它遗漏的工具
# ---------------------------------------------------------------------------

def _find_missed_tools(
    suggested_actions: list[SuggestedAction],
    tools_called: set[str],
) -> list[SuggestedAction]:
    """找出高置信度的预测工具中，LLM 没有调用的。

    只对 NUDGE_TOOLS 中的关键工具进行催促（search_places, trigger_emergency,
    set_language）。其他工具的预处理建议仅供参考，不强制。
    """
    from app.agents.constants import NUDGE_TOOLS
    return [
        a for a in suggested_actions
        if a.confidence >= NUDGE_CONFIDENCE
        and a.tool_name not in tools_called
        and a.tool_name in NUDGE_TOOLS
    ]


def _inject_nudge(
    messages: list[dict],
    last_text: str,
    missed: list[SuggestedAction],
    lang: str,
) -> None:
    """注入催促消息，让 LLM 在下一轮调用遗漏的工具。"""
    # 把 LLM 上一轮的文本回复作为 assistant 消息加入
    if last_text:
        messages.append({"role": "assistant", "content": last_text})

    hints = []
    for a in missed:
        hints.append(f"- {a.tool_name}({json.dumps(a.arguments, ensure_ascii=False)})")

    if lang == "zh":
        nudge_text = (
            "你的回复没有调用工具。根据用户意图分析，你应该调用以下工具：\n"
            + "\n".join(hints)
            + "\n请立即调用对应的工具。不要用文字假装操作已完成。"
        )
    else:
        nudge_text = (
            "Your response did not call any tools. Based on intent analysis, you should call:\n"
            + "\n".join(hints)
            + "\nPlease call the appropriate tools now. Do not pretend the action was completed."
        )

    messages.append({"role": "user", "content": nudge_text})


# ---------------------------------------------------------------------------
# _stream_completion — 流式 LLM 调用
# ---------------------------------------------------------------------------

async def _capture_non_streaming(
    messages: list[dict],
    model: str,
    lang: str,
    round_num: int,
    trace: TraceCollector,
):
    """Parallel non-streaming call to capture the full chat.completion JSON."""
    try:
        import asyncio
        response = await asyncio.wait_for(
            litellm.acompletion(
                model=model,
                messages=messages,
                tools=get_tool_definitions(lang),
                tool_choice="auto",
                temperature=0.3,
                stream=False,
                drop_params=True,
                **llm_extra_kwargs(),
            ),
            timeout=60,
        )
        # Convert litellm response to dict
        raw = response.model_dump() if hasattr(response, "model_dump") else response.to_dict() if hasattr(response, "to_dict") else {"raw": str(response)}
        trace.record_llm_response(round_num, raw)
    except Exception as exc:
        trace.record(f"llm_capture_error_round_{round_num}", str(exc)[:300])


async def _stream_completion(
    messages: list[dict],
    model: str,
    on_token: Callable | None = None,
    lang: str = "zh",
    trace: TraceCollector = INACTIVE_TRACE,
    round_num: int = 0,
) -> tuple[str, list[dict]]:
    """流式调用 LLM，返回 (文本, tool_calls 列表)。"""
    import asyncio

    text_parts = []
    tool_calls_map = {}

    # If trace is active, fire parallel non-streaming call to capture full JSON
    capture_task = None
    if trace.active:
        capture_task = asyncio.create_task(
            _capture_non_streaming(messages, model, lang, round_num, trace)
        )

    try:
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            tools=get_tool_definitions(lang),
            tool_choice="auto",
            temperature=0.3,
            stream=True,
            drop_params=True,
            **llm_extra_kwargs(),
        )

        async for chunk in response:
            delta = chunk.choices[0].delta

            if delta.content:
                text_parts.append(delta.content)
                if on_token:
                    await maybe_await(on_token, delta.content)

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {
                            "id": tc_delta.id or "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    tc = tool_calls_map[idx]
                    if tc_delta.id:
                        tc["id"] = tc_delta.id
                    if tc_delta.function and tc_delta.function.name:
                        tc["function"]["name"] += tc_delta.function.name
                    if tc_delta.function and tc_delta.function.arguments:
                        tc["function"]["arguments"] += tc_delta.function.arguments

    except Exception as exc:
        logger.error("stream_completion_error", extra={"error": str(exc)[:300]})
        if capture_task:
            capture_task.cancel()
        return "".join(text_parts), []

    # Wait for capture task to finish (don't block too long)
    if capture_task:
        try:
            await asyncio.wait_for(capture_task, timeout=30)
        except (asyncio.TimeoutError, Exception):
            pass  # Capture is best-effort

    return "".join(text_parts), [tool_calls_map[i] for i in sorted(tool_calls_map)]


# ---------------------------------------------------------------------------
# run_orchestrator — 统一 Agent Loop 主入口
# ---------------------------------------------------------------------------

async def run_orchestrator(
    message: str,
    system_prompt: str,
    context_messages: list[dict],
    model: str | None = None,
    db=None,
    user_id=None,
    session_id=None,
    on_token: Callable[[str], Awaitable[None]] | None = None,
    on_card: Callable[[dict], Awaitable[None]] | None = None,
    today: str = "",
    suggested_actions: list[SuggestedAction] | None = None,
    trace: TraceCollector = INACTIVE_TRACE,
    **kwargs,
) -> OrchestratorResult:
    """统一的 orchestrator 入口。

    一个 while 循环处理所有场景：
    - 纯聊天（LLM 不调工具 → 直接返回文本）
    - 单/多工具（LLM 返回 tool_calls → dispatch → 喂回结果 → 循环）
    - 图片分析（request_images 作为普通工具处理）
    - Nudge（LLM 遗漏预期工具时催促重试一次）
    """
    lang = kwargs.pop("lang", "zh")
    result = OrchestratorResult()
    use_model = model or settings.model

    # 构建初始消息列表
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(context_messages)

    text_parts: list[str] = []
    nudge_used = False
    plan_nag_used = False

    # 从 kwargs 提取 dispatch_tool 需要的参数
    images = kwargs.pop("images", None)
    image_urls = kwargs.pop("image_urls", None)
    location = kwargs.pop("location", None)
    pets = kwargs.pop("pets", None)

    for round_num in range(MAX_ROUNDS):
        # --- micro_compact：压缩旧的 tool_result ---
        if round_num > 0:
            micro_compact(messages)

        # --- 流式调 LLM ---
        round_text, tool_calls = await _stream_completion(
            messages, use_model, on_token, lang=lang,
            trace=trace, round_num=round_num,
        )

        # --- 没有 tool_calls：检查 plan nag / nudge 或退出 ---
        if not tool_calls:
            text_parts.append(round_text)

            # Plan nag：如果有 plan 但未完成所有步骤，催促 LLM 继续
            if not plan_nag_used and result.plan_steps:
                planned_tools = {s["tool"] for s in result.plan_steps}
                # tools_called 里去掉 plan 本身
                executed_tools = result.tools_called - {"plan"}
                missing_tools = planned_tools - executed_tools
                if missing_tools:
                    plan_nag_used = True
                    missing_steps = [s for s in result.plan_steps if s["tool"] in missing_tools]
                    trace.record("plan_nag_triggered", {
                        "round": round_num,
                        "missing_tools": list(missing_tools),
                        "missing_steps": missing_steps,
                    })
                    logger.info("plan_nag_triggered", extra={
                        "round": round_num,
                        "missing_tools": list(missing_tools),
                    })
                    # 注入 nag 消息
                    if round_text:
                        messages.append({"role": "assistant", "content": round_text})
                    step_list = "\n".join(f"- [{s['id']}] {s['action']} → {s['tool']}" for s in missing_steps)
                    if lang == "zh":
                        nag = f"你的 plan 还有未完成的步骤:\n{step_list}\n请立即调用对应的工具完成这些步骤。"
                    else:
                        nag = f"Your plan has unfinished steps:\n{step_list}\nPlease call the corresponding tools now."
                    messages.append({"role": "user", "content": nag})
                    continue

            # Nudge：如果有高置信度预测但 LLM 从未调用任何工具，催促一次
            # 注意：如果 LLM 已经调过工具（哪怕不是预测的那个），说明它在正常工作，不 nudge
            if not nudge_used and not result.tools_called and suggested_actions:
                missed = _find_missed_tools(suggested_actions, result.tools_called)
                if missed:
                    nudge_used = True
                    trace.record("nudge_triggered", {
                        "round": round_num,
                        "missed_tools": [a.tool_name for a in missed],
                    })
                    logger.info("nudge_triggered", extra={
                        "round": round_num,
                        "missed_tools": [a.tool_name for a in missed],
                    })
                    _inject_nudge(messages, round_text, missed, lang)
                    continue

            break  # 正常退出循环

        # --- 有 tool_calls：构建 assistant 消息并逐个执行 ---
        text_parts.append(round_text)

        assistant_msg = {
            "role": "assistant",
            "content": round_text or None,
            "tool_calls": tool_calls,
        }
        messages.append(assistant_msg)

        # If introduce_product is among the tool calls, skip all other tools
        # (LLM sometimes incorrectly records events when user is just asking about features)
        tool_names_in_round = {tc["function"]["name"] for tc in tool_calls}
        if "introduce_product" in tool_names_in_round and len(tool_calls) > 1:
            tool_calls = [tc for tc in tool_calls if tc["function"]["name"] == "introduce_product"]

        for tc in tool_calls:
            tool_result = await dispatch_tool(
                tc, db, user_id, session_id, result, on_card, lang,
                pets=pets, images=images, image_urls=image_urls,
                location=location, _messages=messages,
            )

            trace.record("tool_dispatch", {
                "round": round_num,
                "tool": tc["function"]["name"],
                "args": tc["function"]["arguments"],
                "result_keys": list(tool_result.keys()),
                "success": tool_result.get("success"),
                "error": tool_result.get("error"),
            })

            # 序列化 tool_result（去掉内部标记字段）
            serializable = {k: v for k, v in tool_result.items() if not k.startswith("_")}
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(serializable, ensure_ascii=False, default=str),
            })

            # 如果 request_images 返回了图片，注入到消息中
            if "_inject_images" in tool_result:
                image_content = [
                    {"type": "text", "text": "这是用户附带的图片，请仔细查看后回答：" if lang == "zh" else "Here are the user's images:"}
                ]
                for img_b64 in tool_result["_inject_images"]:
                    image_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    })
                messages.append({"role": "user", "content": image_content})

    # 确保 response_text 不为空（除非有 confirm card 待处理）
    import re as _re
    raw_text = "".join(text_parts)
    # Strip leaked XML/HTML tags from LLM output (grok sometimes outputs <parameter> or <xai:function_call>)
    result.response_text = _re.sub(r"</?(?:parameter|xai:function_call|function_call)[^>]*>", "", raw_text).strip()
    if not result.response_text.strip() and not result.confirm_cards and not result.cards:
        fallback = t("fallback_error", lang)
        result.response_text = fallback
        if on_token:
            await maybe_await(on_token, fallback)

    return result
