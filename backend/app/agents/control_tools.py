"""Control-flow tools handled by the orchestrator instead of tool handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agents.tool_context import ToolDispatchContext
from app.agents.tool_invocation import ToolInvocation


def handle_control_tool(
    invocation: ToolInvocation,
    context: ToolDispatchContext,
    *,
    load_images_from_urls: Callable[[list[str]], list[str]],
) -> dict[str, Any] | None:
    """Handle orchestrator-owned tools, returning None for normal tools."""
    if invocation.name == "plan":
        steps = invocation.arguments.get("steps", [])
        if context.result is not None:
            context.result.plan_steps = steps
        step_summary = "; ".join(f"[{s.get('id')}] {s.get('action')}" for s in steps)
        return {
            "status": "planned",
            "message": f"已规划 {len(steps)} 个步骤: {step_summary}",
            "steps": steps,
        }

    if invocation.name == "request_images":
        if context.images:
            return {
                "status": "images_loaded",
                "message": "图片已加载" if context.lang == "zh" else "Images loaded",
                "_inject_images": context.images,
            }
        if context.recent_image_urls:
            history_images = load_images_from_urls(context.recent_image_urls)
            if history_images:
                return {
                    "status": "images_loaded",
                    "message": (
                        "已加载历史消息中的图片" if context.lang == "zh"
                        else "Loaded images from previous messages"
                    ),
                    "_inject_images": history_images,
                }
        return {
            "error": "用户没有附带图片" if context.lang == "zh" else "No images attached",
        }

    return None
