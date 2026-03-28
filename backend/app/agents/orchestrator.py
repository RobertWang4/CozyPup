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
from app.agents.constants import CONFIRM_TOOLS, maybe_await
from app.config import settings
from app.agents.executor import run_executor, ExecutorResult
from app.agents.locale import t
from app.database import async_session
from app.agents.tools import execute_tool, get_tool_definitions
from app.agents.validation import validate_tool_args
from app.agents.pending_actions import store_action

logger = logging.getLogger(__name__)


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
    if fn_name == "draft_email":
        return t("desc_draft_email", lang).format(subject=fn_args.get('subject', ''))
    if fn_name == "save_pet_profile_md":
        return t("desc_save_profile", lang).format(label=label)
    if fn_name == "set_pet_avatar":
        return t("desc_set_avatar", lang).format(label=label)
    if fn_name == "upload_event_photo":
        return t("desc_upload_photo", lang)
    return fn_name

MAX_TOOL_ROUNDS = 3


@dataclass
class OrchestratorResult:
    """Result from orchestrator execution."""
    response_text: str = ""
    cards: list[dict] = field(default_factory=list)
    confirm_cards: list[dict] = field(default_factory=list)
    executor_results: list[ExecutorResult] = field(default_factory=list)


async def _execute_tool_call(
    fn_name: str,
    fn_args: dict,
    db,
    user_id,
    session_id=None,
    on_card=None,
    result: OrchestratorResult | None = None,
    lang: str = "zh",
    **kwargs,
) -> dict | None:
    """Validate, check confirm gate, execute a single tool call.

    Returns:
        tool_result dict on success.
        None if a confirm card was queued (tool not executed).
    Raises:
        ValueError if validation fails.
    """
    # Confirm gate — destructive tools need user approval
    if fn_name in CONFIRM_TOOLS and session_id:
        desc = _describe_tool_call(fn_name, fn_args, lang=lang)
        action_id = await store_action(
            db=db, user_id=str(user_id), session_id=str(session_id),
            tool_name=fn_name, arguments=fn_args, description=desc,
        )
        confirm_card = {"type": "confirm_action", "action_id": action_id, "message": desc}
        if result:
            result.confirm_cards.append(confirm_card)
        if on_card:
            await maybe_await(on_card, confirm_card)
        return None  # Signal: confirm pending

    # Validate
    errors = validate_tool_args(fn_name, fn_args)
    if errors:
        raise ValueError("; ".join(errors))

    # Execute — strip lang from kwargs to avoid duplicate keyword argument
    tool_kwargs = {k: v for k, v in kwargs.items() if k != "lang"}
    tool_result = await execute_tool(fn_name, fn_args, db, user_id, **tool_kwargs)
    await db.commit()

    # Handle needs_confirm (gender/species first-time set)
    if tool_result.get("needs_confirm") and session_id:
        confirm_tool = tool_result.get("confirm_tool", fn_name)
        confirm_args = tool_result.get("confirm_arguments", fn_args)
        confirm_desc = tool_result.get("confirm_description", f"确认执行 {fn_name}")
        action_id = await store_action(
            db=db, user_id=str(user_id), session_id=str(session_id),
            tool_name=confirm_tool, arguments=confirm_args, description=confirm_desc,
        )
        confirm_card = {"type": "confirm_action", "action_id": action_id, "message": confirm_desc}
        if result:
            result.confirm_cards.append(confirm_card)
        if on_card:
            await maybe_await(on_card, confirm_card)
        return tool_result  # Return result (may have saved non-lockable fields)

    # Push card
    card = tool_result.get("card")
    if card:
        if result:
            result.cards.append(card)
        if on_card:
            await maybe_await(on_card, card)

    return tool_result


async def _ensure_response(result, on_token, lang: str = "zh"):
    """Ensure response_text is never empty — stream fallback if needed.
    Skip fallback when confirm cards are pending (empty text is expected)."""
    if result.confirm_cards:
        return
    if not result.response_text.strip():
        fallback = t("fallback_error", lang)
        result.response_text = fallback
        if on_token:
            await maybe_await(on_token, fallback)


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
    use_model = model or settings.model
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
        logger.error("orchestrator_stream_error", extra={"error": str(exc)})
        error_msg = t("orchestrator_stream_error_msg", lang)
        if on_token:
            await maybe_await(on_token, error_msg)
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
        await _ensure_response(result, on_token, lang=lang)
        return result

    # PATH C: Multi task — parallel executors
    result = await _handle_multi_task(
        tool_calls, initial_text, use_model, db, user_id, session_id,
        on_token, on_card, today, **kwargs,
    )

    await _ensure_response(result, on_token, lang=lang)

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
        logger.warning("arg_parse_error", extra={"error": str(exc), "fn_name": fn_name})
        result.response_text = initial_text or t("arg_parse_error", lang)
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

    # Special: request_images — handled by _handle_request_images_then_continue
    # (should not reach here due to early check, but just in case)
    if fn_name == "request_images":
        result = await _handle_request_images_then_continue(
            tool_call, messages, initial_text, model,
            db, user_id, session_id, on_token, on_card, "", **kwargs,
        )
        return result

    # Confirm gate (pre-execution, before entering the multi-round loop)
    if fn_name in CONFIRM_TOOLS:
        try:
            await _execute_tool_call(
                fn_name, fn_args, db, user_id,
                session_id=session_id, on_card=on_card, result=result, lang=lang, **kwargs,
            )
        except ValueError:
            pass  # confirm tools skip validation
        result.response_text = "".join(text_parts)
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
            tool_result = await _execute_tool_call(
                current_fn_name, current_fn_args, db, user_id,
                session_id=session_id, on_card=on_card, result=result, lang=lang, **kwargs,
            )

            # Handle needs_confirm (tool executed partially, pending user confirmation)
            if tool_result is not None and tool_result.get("needs_confirm"):
                confirm_desc = tool_result.get("confirm_description", f"确认执行 {current_fn_name}")
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

            # Validate next tool (validation errors break the loop, no retry for follow-ups)
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
                try:
                    await _execute_tool_call(
                        next_fn, next_args, db, user_id,
                        session_id=session_id, on_card=on_card, result=result, lang=lang, **kwargs,
                    )
                except ValueError:
                    pass  # confirm tools skip validation
                break

            # Continue loop with next tool
            current_tool_call = next_tc
            current_fn_name = next_fn
            current_fn_args = next_args
            current_text = followup_text

        except ValueError as ve:
            # Validation error from _execute_tool_call — shouldn't happen on first round
            # (already validated above) but may happen on follow-up rounds
            logger.error("orchestrator_validation_error", extra={
                "tool": current_fn_name, "error": str(ve), "round": _round,
            })
            error_text = f"\n参数验证失败: {ve}"
            text_parts.append(error_text)
            break
        except Exception as exc:
            logger.error("orchestrator_tool_error", extra={
                "tool": current_fn_name, "error": str(exc), "round": _round,
            })
            error_text = f"\n{t('tool_execution_error', lang)}"
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

                if db and user_id:
                    try:
                        tool_result = await _execute_tool_call(
                            fn_name, fn_args, db, user_id,
                            session_id=session_id, on_card=on_card, result=result,
                            lang=lang, **kwargs,
                        )
                        if tool_result is not None:
                            messages.append({
                                "role": "tool", "tool_call_id": tc["id"],
                                "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                            })
                        else:
                            messages.append({
                                "role": "tool", "tool_call_id": tc["id"],
                                "content": json.dumps({"status": "waiting_confirm"}),
                            })
                    except ValueError as ve:
                        messages.append({
                            "role": "tool", "tool_call_id": tc["id"],
                            "content": json.dumps({"error": str(ve)}),
                        })
                    except Exception as exc:
                        logger.error("image_followup_tool_error", extra={"tool": fn_name, "error": str(exc)})
                        messages.append({
                            "role": "tool", "tool_call_id": tc["id"],
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
                    try:
                        await _execute_tool_call(
                            ft_name, ft_args, db, user_id,
                            session_id=session_id, on_card=on_card, result=result,
                            lang=lang, **kwargs,
                        )
                    except ValueError as ve:
                        logger.error("image_followup_extra_validation", extra={"tool": ft_name, "error": str(ve)[:200]})
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
        await _ensure_response(result, on_token, lang=lang)
        return result

    # Run executors in parallel — each gets its own DB session for concurrency safety
    executor_coros = []
    for task in tasks:
        coro = run_executor(
            task_description=task["description"],
            context=json.dumps(task["args"], ensure_ascii=False),
            available_tools=[task["name"]],
            db_factory=async_session,
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
            summaries.append(t("multi_task_failed", lang).format(tool=tasks[i]["name"]))
            continue

        result.executor_results.append(exec_result)

        if exec_result.needs_confirm:
            if session_id:
                action_id = await store_action(
                    db=db,
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
                    await maybe_await(on_card, confirm_card)
            summaries.append(f"⏳ {exec_result.description} (等待确认)")

        elif exec_result.success:
            if exec_result.card:
                result.cards.append(exec_result.card)
                if on_card:
                    await maybe_await(on_card, exec_result.card)
            summaries.append(f"✅ {exec_result.summary}")

        else:
            summaries.append(t("executor_failed", lang).format(error=exec_result.error or t("execution_failed", lang)))

    # If ALL tasks need confirmation, skip LLM summary — just return with confirm cards
    all_confirm = result.confirm_cards and not result.cards
    if all_confirm:
        return result

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

    try:
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
        logger.error("stream_completion_error", extra={"error": str(exc)})
        return "".join(text_parts), []

    return "".join(text_parts), [tool_calls_map[i] for i in sorted(tool_calls_map)]
