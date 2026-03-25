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

from app.config import settings
from app.agents.executor import run_executor, ExecutorResult
from app.agents.tools import TOOL_DEFINITIONS, execute_tool
from app.agents.validation import validate_tool_args
from app.agents.pending_actions import store_action

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
    result = OrchestratorResult()
    use_model = model or settings.orchestrator_model

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
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            temperature=0.3,
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

    # PATH B: Single task — fast path
    if len(tool_calls) == 1:
        result = await _handle_single_task(
            tool_calls[0], messages, initial_text, use_model,
            db, user_id, session_id, on_token, on_card, **kwargs,
        )
        return result

    # PATH C: Multi task — parallel executors
    result = await _handle_multi_task(
        tool_calls, initial_text, db, user_id, session_id,
        on_token, on_card, today, **kwargs,
    )
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
            messages, model, on_token
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
            action_id = store_action(
                user_id=str(user_id),
                session_id=str(session_id),
                tool_name=fn_name,
                arguments=fn_args,
                description=f"确认执行: {fn_name}",
            )
            confirm_card = {
                "type": "confirm_action",
                "action_id": action_id,
                "message": f"确认执行: {fn_name}({json.dumps(fn_args, ensure_ascii=False)})",
            }
            result.confirm_cards.append(confirm_card)
            if on_card:
                await _maybe_await(on_card, confirm_card)

        result.response_text = "".join(text_parts)
        return result

    # Execute tool
    if db and user_id:
        try:
            tool_result = await execute_tool(fn_name, fn_args, db, user_id, **kwargs)
            await db.commit()

            card = tool_result.get("card")
            if card:
                result.cards.append(card)
                if on_card:
                    await _maybe_await(on_card, card)

            # Generate follow-up response with tool result
            messages.append({
                "role": "assistant",
                "content": initial_text or None,
                "tool_calls": [tool_call],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(tool_result, ensure_ascii=False, default=str),
            })

            followup_text, _ = await _stream_completion(
                messages, model, on_token
            )
            text_parts.append(followup_text)

        except Exception as exc:
            logger.error("orchestrator_tool_error", extra={
                "tool": fn_name, "error": str(exc)
            })
            error_text = f"\n工具执行出错: {exc}"
            text_parts.append(error_text)

    result.response_text = "".join(text_parts)
    return result


async def _handle_multi_task(
    tool_calls: list[dict],
    initial_text: str,
    db, user_id, session_id,
    on_token, on_card,
    today: str = "",
    **kwargs,
) -> OrchestratorResult:
    """Multi-task path: dispatch parallel executors."""
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

    # Append summaries to response
    if summaries and on_token:
        summary_text = "\n" + "\n".join(summaries)
        await _maybe_await(on_token, summary_text)
        result.response_text += summary_text

    return result


async def _stream_completion(
    messages: list[dict],
    model: str,
    on_token=None,
) -> tuple[str, list[dict]]:
    """Stream a completion, return (text, tool_calls)."""
    text_parts = []
    tool_calls_map = {}

    response = await litellm.acompletion(
        model=model,
        messages=messages,
        tools=TOOL_DEFINITIONS,
        tool_choice="auto",
        temperature=0.3,
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
