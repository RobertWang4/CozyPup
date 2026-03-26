"""
Orchestrator Agent: Main agent that understands intent and dispatches executors.

Three execution paths:
  A. Pure chat — no tools, stream response directly
  B. Single task — fast path, orchestrator calls tool itself
  C. Multi task — dispatch parallel executors, collect results, generate summary
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Callable, Awaitable

import litellm

from app.agents import llm_extra_kwargs
from app.config import settings
from app.agents.executor import run_executor, ExecutorResult
from app.agents.tools import TOOL_DEFINITIONS, execute_tool, get_tool_definitions
from app.agents.validation import validate_tool_args
from app.agents.pending_actions import store_action
from app.agents.chat_agent import _describe_tool_call

logger = logging.getLogger(__name__)

CONFIRM_TOOLS = {"delete_pet", "delete_calendar_event", "delete_reminder"}
MAX_TOOL_ROUNDS = 3


@dataclass
class OrchestratorResult:
    """Result from orchestrator execution."""
    response_text: str = ""
    cards: list[dict] = field(default_factory=list)
    confirm_cards: list[dict] = field(default_factory=list)
    executor_results: list[ExecutorResult] = field(default_factory=list)


async def _maybe_await(fn, *args):
    result = fn(*args)
    if asyncio.iscoroutine(result):
        return await result
    return result


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
    **kwargs,
) -> OrchestratorResult:
    """
    Main orchestrator entry point.

    Streams text via on_token callback, pushes cards via on_card callback.
    Returns structured result with all cards and executor outputs.
    """
    lang = kwargs.get("lang", "zh")
    result = OrchestratorResult()
    use_model = model or settings.orchestrator_model
    tool_defs = get_tool_definitions(lang)

    # Build messages
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(context_messages)

    # Stream the initial LLM response
    text_parts = []
    tool_calls_map = {}

    try:
        response = await litellm.acompletion(
            model=use_model,
            messages=messages,
            tools=tool_defs,
            tool_choice="auto",
            temperature=0.3,
            stream=True,
            **llm_extra_kwargs(),
        )

        async for chunk in response:
            delta = chunk.choices[0].delta

            if delta.content:
                text_parts.append(delta.content)
                if on_token:
                    await _maybe_await(on_token, delta.content)

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
        logger.error("orchestrator_stream_error", extra={"error": str(exc)})
        error_msg = "抱歉，处理请求时出现错误，请稍后重试。"
        if on_token:
            await _maybe_await(on_token, error_msg)
        result.response_text = error_msg
        return result

    tool_calls = [tool_calls_map[i] for i in sorted(tool_calls_map)]
    initial_text = "".join(text_parts)

    # PATH A: Pure chat — no tools
    if not tool_calls:
        result.response_text = initial_text
        return result

    # If request_images is among tool calls, handle it first, then re-run
    has_request_images = any(
        tc["function"]["name"] == "request_images" for tc in tool_calls
    )
    if has_request_images:
        # Find the request_images call
        ri_tc = next(tc for tc in tool_calls if tc["function"]["name"] == "request_images")
        # Handle images first, then let LLM decide next steps (may call tools)
        result = await _handle_request_images_then_continue(
            ri_tc, messages, initial_text, use_model,
            db, user_id, session_id, on_token, on_card, today, **kwargs,
        )
        return result

    # PATH B: Single task — fast path
    if len(tool_calls) == 1:
        result = await _handle_single_task(
            tool_calls[0], messages, initial_text, use_model,
            db, user_id, session_id, on_token, on_card, **kwargs,
        )
        if not result.response_text.strip():
            fallback = "抱歉，处理时遇到了问题，请再说一次。"
            result.response_text = fallback
            if on_token:
                await _maybe_await(on_token, fallback)
        return result

    # PATH C: Multi task — parallel executors
    result = await _handle_multi_task(
        tool_calls, initial_text, use_model, db, user_id, session_id,
        on_token, on_card, today, **kwargs,
    )

    # Final safeguard: never return empty response
    if not result.response_text.strip():
        fallback = "抱歉，处理时遇到了问题，请再说一次。"
        result.response_text = fallback
        if on_token:
            await _maybe_await(on_token, fallback)

    return result


async def _handle_single_task(
    tool_call: dict,
    messages: list[dict],
    initial_text: str,
    model: str,
    db, user_id, session_id,
    on_token, on_card,
    **kwargs,
) -> OrchestratorResult:
    """Fast path: orchestrator handles single tool call directly."""
    lang = kwargs.get("lang", "zh")
    result = OrchestratorResult()
    text_parts = [initial_text] if initial_text else []

    fn_name = tool_call["function"]["name"]

    try:
        fn_args = json.loads(tool_call["function"]["arguments"])
    except json.JSONDecodeError as exc:
        result.response_text = initial_text or f"参数解析错误: {exc}"
        return result

    # Validate
    errors = validate_tool_args(fn_name, fn_args)
    if errors:
        # Feed back to LLM for one retry
        messages.append({
            "role": "assistant",
            "content": initial_text or None,
            "tool_calls": [tool_call],
        })
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": json.dumps({"error": "; ".join(errors)}),
        })

        # Retry with streaming
        retry_text, retry_tools = await _stream_completion(
            messages, model, on_token, lang=lang
        )

        if retry_tools:
            fn_name = retry_tools[0]["function"]["name"]
            try:
                fn_args = json.loads(retry_tools[0]["function"]["arguments"])
            except json.JSONDecodeError:
                result.response_text = retry_text or "重试失败"
                return result

            errors = validate_tool_args(fn_name, fn_args)
            if errors:
                result.response_text = retry_text or "参数验证失败"
                return result

            text_parts = [retry_text] if retry_text else text_parts
        else:
            result.response_text = retry_text
            return result

    # Confirm gate
    if fn_name in CONFIRM_TOOLS:
        if session_id:
            desc = _describe_tool_call(fn_name, fn_args, lang=lang)
            action_id = store_action(
                user_id=str(user_id),
                session_id=str(session_id),
                tool_name=fn_name,
                arguments=fn_args,
                description=desc,
            )
            confirm_card = {
                "type": "confirm_action",
                "action_id": action_id,
                "message": desc,
            }
            result.confirm_cards.append(confirm_card)
            if on_card:
                await _maybe_await(on_card, confirm_card)

        result.response_text = "".join(text_parts)
        return result

    # Special: request_images — handled by _handle_request_images_then_continue
    # (should not reach here due to early check, but just in case)
    if fn_name == "request_images":
        result = await _handle_request_images_then_continue(
            tool_call, messages, initial_text, model,
            db, user_id, session_id, on_token, on_card, "", **kwargs,
        )
        return result

    # Execute tool with multi-round loop (like chat_agent)
    current_tool_call = tool_call
    current_fn_name = fn_name
    current_fn_args = fn_args
    current_text = initial_text

    for _round in range(MAX_TOOL_ROUNDS):
        if not (db and user_id):
            break

        try:
            # Execute the tool
            tool_result = await execute_tool(current_fn_name, current_fn_args, db, user_id, **kwargs)
            await db.commit()

            # Handle needs_confirm (e.g. gender/species first-time set)
            if tool_result.get("needs_confirm") and session_id:
                confirm_tool = tool_result.get("confirm_tool", current_fn_name)
                confirm_args = tool_result.get("confirm_arguments", current_fn_args)
                confirm_desc = tool_result.get("confirm_description", f"确认执行 {current_fn_name}")
                action_id = store_action(
                    user_id=str(user_id),
                    session_id=str(session_id),
                    tool_name=confirm_tool,
                    arguments=confirm_args,
                    description=confirm_desc,
                )
                confirm_card = {
                    "type": "confirm_action",
                    "action_id": action_id,
                    "message": confirm_desc,
                }
                result.confirm_cards.append(confirm_card)
                if on_card:
                    await _maybe_await(on_card, confirm_card)
                messages.append({
                    "role": "assistant",
                    "content": current_text or None,
                    "tool_calls": [current_tool_call],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": current_tool_call["id"],
                    "content": json.dumps({"status": "pending_user_confirmation", "message": confirm_desc}),
                })
                break

            card = tool_result.get("card")
            if card:
                result.cards.append(card)
                if on_card:
                    await _maybe_await(on_card, card)

            # Feed tool result back to LLM
            messages.append({
                "role": "assistant",
                "content": current_text or None,
                "tool_calls": [current_tool_call],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": current_tool_call["id"],
                "content": json.dumps(tool_result, ensure_ascii=False, default=str),
            })

            # Get follow-up — may include more tool calls
            followup_text, followup_tools = await _stream_completion(
                messages, model, on_token, lang=lang
            )
            text_parts.append(followup_text)

            if not followup_tools:
                break  # No more tools, done

            # Process next tool call
            next_tc = followup_tools[0]
            next_fn = next_tc["function"]["name"]
            try:
                next_args = json.loads(next_tc["function"]["arguments"])
            except json.JSONDecodeError:
                break

            # Validate next tool
            next_errors = validate_tool_args(next_fn, next_args)
            if next_errors:
                messages.append({
                    "role": "assistant",
                    "content": followup_text or None,
                    "tool_calls": [next_tc],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": next_tc["id"],
                    "content": json.dumps({"error": "; ".join(next_errors)}),
                })
                break

            # Confirm gate for next tool
            if next_fn in CONFIRM_TOOLS:
                if session_id:
                    desc = _describe_tool_call(next_fn, next_args, lang=lang)
                    action_id = store_action(
                        user_id=str(user_id),
                        session_id=str(session_id),
                        tool_name=next_fn,
                        arguments=next_args,
                        description=desc,
                    )
                    confirm_card = {
                        "type": "confirm_action",
                        "action_id": action_id,
                        "message": desc,
                    }
                    result.confirm_cards.append(confirm_card)
                    if on_card:
                        await _maybe_await(on_card, confirm_card)
                break

            # Continue loop with next tool
            current_tool_call = next_tc
            current_fn_name = next_fn
            current_fn_args = next_args
            current_text = followup_text

        except Exception as exc:
            logger.error("orchestrator_tool_error", extra={
                "tool": current_fn_name, "error": str(exc), "round": _round,
            })
            error_text = f"\n工具执行出错: {exc}"
            text_parts.append(error_text)
            break

    result.response_text = "".join(text_parts)
    return result


async def _handle_request_images_then_continue(
    ri_tool_call: dict,
    messages: list[dict],
    initial_text: str,
    model: str,
    db, user_id, session_id,
    on_token, on_card,
    today: str = "",
    **kwargs,
) -> OrchestratorResult:
    """Handle request_images, then allow LLM to call follow-up tools (e.g. create_calendar_event)."""
    lang = kwargs.get("lang", "zh")
    result = OrchestratorResult()
    text_parts = [initial_text] if initial_text else []

    images = kwargs.get("images") or []
    messages.append({
        "role": "assistant",
        "content": initial_text or None,
        "tool_calls": [ri_tool_call],
    })

    if images:
        image_content = [{"type": "text", "text": "这是用户附带的图片，请仔细查看后回答："}]
        for img_b64 in images:
            image_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
            })
        messages.append({
            "role": "tool",
            "tool_call_id": ri_tool_call["id"],
            "content": "图片已加载，请查看对话中的图片。",
        })
        messages.append({
            "role": "user",
            "content": image_content,
        })
    else:
        messages.append({
            "role": "tool",
            "tool_call_id": ri_tool_call["id"],
            "content": json.dumps({"error": "用户没有附带图片"}),
        })

    # Follow-up: LLM sees the image and may call tools (e.g. create_calendar_event)
    followup_text, followup_tools = await _stream_completion(messages, model, on_token, lang=lang)
    text_parts.append(followup_text)

    # If LLM wants to call tools after seeing the image, execute them
    if followup_tools:
        # Filter out request_images if LLM calls it again
        real_tools = [tc for tc in followup_tools if tc["function"]["name"] != "request_images"]
        if real_tools:
            # Add assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": followup_text or None,
                "tool_calls": real_tools,
            })

            for tc in real_tools:
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    continue

                # Confirm gate
                if fn_name in CONFIRM_TOOLS:
                    if session_id:
                        action_id = store_action(
                            user_id=str(user_id),
                            session_id=str(session_id),
                            tool_name=fn_name,
                            arguments=fn_args,
                            description=_describe_tool_call(fn_name, fn_args, lang=lang),
                        )
                        confirm_card = {
                            "type": "confirm_action",
                            "action_id": action_id,
                            "message": _describe_tool_call(fn_name, fn_args, lang=lang),
                        }
                        result.confirm_cards.append(confirm_card)
                        if on_card:
                            await _maybe_await(on_card, confirm_card)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps({"status": "waiting_confirm"}),
                    })
                    continue

                # Validate
                errors = validate_tool_args(fn_name, fn_args)
                if errors:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps({"error": "; ".join(errors)}),
                    })
                    continue

                # Execute
                if db and user_id:
                    try:
                        tool_result = await execute_tool(fn_name, fn_args, db, user_id, **kwargs)
                        await db.commit()
                        card = tool_result.get("card")
                        if card:
                            result.cards.append(card)
                            if on_card:
                                await _maybe_await(on_card, card)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                        })
                    except Exception as exc:
                        logger.error("image_followup_tool_error", extra={
                            "tool": fn_name, "error": str(exc)
                        })
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps({"error": str(exc)}),
                        })

            # Generate final summary — may include more tool calls
            final_text, final_tools = await _stream_completion(messages, model, on_token, lang=lang)
            text_parts.append(final_text)

            # Execute any follow-up tools after image viewing
            if final_tools and db and user_id:
                for ft in final_tools:
                    ft_name = ft["function"]["name"]
                    try:
                        ft_args = json.loads(ft["function"]["arguments"])
                    except json.JSONDecodeError:
                        continue
                    if ft_name in CONFIRM_TOOLS and session_id:
                        desc = _describe_tool_call(ft_name, ft_args, lang=lang)
                        aid = store_action(user_id=str(user_id), session_id=str(session_id),
                                           tool_name=ft_name, arguments=ft_args, description=desc)
                        cc = {"type": "confirm_action", "action_id": aid, "message": desc}
                        result.confirm_cards.append(cc)
                        if on_card:
                            await _maybe_await(on_card, cc)
                        continue
                    try:
                        tr = await execute_tool(ft_name, ft_args, db, user_id, **kwargs)
                        await db.commit()
                        if tr.get("card"):
                            result.cards.append(tr["card"])
                            if on_card:
                                await _maybe_await(on_card, tr["card"])
                    except Exception as exc:
                        logger.error("image_followup_extra_error", extra={"tool": ft_name, "error": str(exc)[:200]})

    result.response_text = "".join(text_parts)
    return result


async def _handle_multi_task(
    tool_calls: list[dict],
    initial_text: str,
    model: str,
    db, user_id, session_id,
    on_token, on_card,
    today: str = "",
    **kwargs,
) -> OrchestratorResult:
    """Multi-task path: dispatch parallel executors."""
    lang = kwargs.get("lang", "zh")
    result = OrchestratorResult()
    result.response_text = initial_text or ""

    # Parse all tool calls into executor tasks
    tasks = []
    for tc in tool_calls:
        fn_name = tc["function"]["name"]
        try:
            fn_args = json.loads(tc["function"]["arguments"])
        except json.JSONDecodeError:
            continue

        tasks.append({
            "name": fn_name,
            "args": fn_args,
            "description": f"执行 {fn_name}: {json.dumps(fn_args, ensure_ascii=False)}",
        })

    if not tasks:
        if not result.response_text.strip():
            fallback = "抱歉，我没能理解你的请求，请再试一次。"
            result.response_text = fallback
            if on_token:
                await _maybe_await(on_token, fallback)
        return result

    # Run executors in parallel
    executor_coros = []
    for task in tasks:
        coro = run_executor(
            task_description=task["description"],
            context=json.dumps(task["args"], ensure_ascii=False),
            available_tools=[task["name"]],
            db=db,
            user_id=user_id,
            today=today,
            **kwargs,
        )
        executor_coros.append(coro)

    executor_results = await asyncio.gather(*executor_coros, return_exceptions=True)

    # Process results
    summaries = []
    for i, exec_result in enumerate(executor_results):
        if isinstance(exec_result, Exception):
            logger.error("executor_exception", extra={
                "task": tasks[i]["name"], "error": str(exec_result)
            })
            summaries.append(f"❌ {tasks[i]['name']}: 执行失败")
            continue

        result.executor_results.append(exec_result)

        if exec_result.needs_confirm:
            if session_id:
                action_id = store_action(
                    user_id=str(user_id),
                    session_id=str(session_id),
                    tool_name=exec_result.tool,
                    arguments=exec_result.arguments,
                    description=exec_result.description,
                )
                confirm_card = {
                    "type": "confirm_action",
                    "action_id": action_id,
                    "message": exec_result.description,
                }
                result.confirm_cards.append(confirm_card)
                if on_card:
                    await _maybe_await(on_card, confirm_card)
            summaries.append(f"⏳ {exec_result.description} (等待确认)")

        elif exec_result.success:
            if exec_result.card:
                result.cards.append(exec_result.card)
                if on_card:
                    await _maybe_await(on_card, exec_result.card)
            summaries.append(f"✅ {exec_result.summary}")

        else:
            summaries.append(f"❌ {exec_result.error or '执行失败'}")

    # Generate natural language summary via LLM (not raw technical output)
    if summaries:
        summary_prompt = "你刚才执行了以下操作，请用简短温暖的语气告诉用户结果：\n" + "\n".join(summaries)
        followup_msgs = [
            *[{"role": "system", "content": "用简短温暖的语气总结操作结果，不要列出工具名称。"}],
            {"role": "user", "content": summary_prompt},
        ]
        # Summary-only call — tool_calls intentionally discarded (all tools already executed)
        followup_text, _ = await _stream_completion(followup_msgs, model, on_token, lang=lang)
        result.response_text += followup_text

    return result


async def _stream_completion(
    messages: list[dict],
    model: str,
    on_token=None,
    lang: str = "zh",
) -> tuple[str, list[dict]]:
    """Stream a completion, return (text, tool_calls)."""
    text_parts = []
    tool_calls_map = {}

    response = await litellm.acompletion(
        model=model,
        messages=messages,
        tools=get_tool_definitions(lang),
        tool_choice="auto",
        temperature=0.3,
        **llm_extra_kwargs(),
        stream=True,
    )

    async for chunk in response:
        delta = chunk.choices[0].delta

        if delta.content:
            text_parts.append(delta.content)
            if on_token:
                await _maybe_await(on_token, delta.content)

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

    return "".join(text_parts), [tool_calls_map[i] for i in sorted(tool_calls_map)]
