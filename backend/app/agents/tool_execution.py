"""Validation, execution, commit, and post-execution effects for tools."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.agents.constants import maybe_await
from app.agents.pending_actions import store_action
from app.agents.tool_context import ToolDispatchContext
from app.agents.tool_invocation import ToolInvocation
from app.agents.tool_memory import sync_tool_memory
from app.agents.tools import execute_tool
from app.agents.validation import validate_tool_args

logger = logging.getLogger(__name__)


ValidateFn = Callable[[str, dict], list[str]]
ExecuteFn = Callable[..., Awaitable[dict[str, Any]]]
StoreActionFn = Callable[..., Awaitable[str]]
MemorySyncFn = Callable[[ToolInvocation, dict[str, Any]], None]


async def handle_tool_execution(
    invocation: ToolInvocation,
    context: ToolDispatchContext,
    *,
    validate: ValidateFn = validate_tool_args,
    execute: ExecuteFn = execute_tool,
    store_pending_action: StoreActionFn = store_action,
    sync_memory: MemorySyncFn = sync_tool_memory,
) -> dict[str, Any]:
    """Validate, execute, commit, sync memory, and emit post-execution cards."""
    fn_name = invocation.name
    fn_args = invocation.arguments

    errors = validate(fn_name, fn_args)
    if errors:
        return {"error": "; ".join(errors)}

    try:
        exec_kwargs = {"lang": context.lang}
        if context.location is not None:
            exec_kwargs["location"] = context.location
        effective_image_urls = context.image_urls or context.recent_image_urls
        if effective_image_urls:
            exec_kwargs["image_urls"] = effective_image_urls

        tool_result = await execute(
            fn_name,
            fn_args,
            context.db,
            context.user_id,
            **exec_kwargs,
        )
        await context.db.commit()
        if tool_result.get("success") and context.result is not None:
            context.result.tools_executed.add(fn_name)
    except Exception as exc:
        logger.error("dispatch_tool_error", extra={
            "tool": fn_name,
            "error": str(exc)[:300],
        })
        return {"error": str(exc)[:200]}

    sync_memory(invocation, tool_result)

    if tool_result.get("needs_confirm") and context.session_id:
        confirm_tool = tool_result.get("confirm_tool", fn_name)
        confirm_args = tool_result.get("confirm_arguments", fn_args)
        confirm_desc = tool_result.get("confirm_description", f"确认执行 {fn_name}")
        action_id = await store_pending_action(
            db=context.db,
            user_id=str(context.user_id),
            session_id=str(context.session_id),
            tool_name=confirm_tool,
            arguments=confirm_args,
            description=confirm_desc,
        )
        card = {"type": "confirm_action", "action_id": action_id, "message": confirm_desc}
        if context.result is not None:
            context.result.confirm_cards.append(card)
        if context.on_card:
            await maybe_await(context.on_card, card)
        return tool_result

    card = tool_result.get("card")
    if card:
        if context.result is not None:
            context.result.cards.append(card)
        if context.on_card:
            await maybe_await(context.on_card, card)

    return tool_result
