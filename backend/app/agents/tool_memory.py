"""Memory synchronization hooks for tool execution results."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agents.tool_invocation import ToolInvocation


def sync_tool_memory(
    invocation: ToolInvocation,
    tool_result: dict[str, Any],
    *,
    schedule_upsert: Callable[[str], None] | None = None,
    schedule_delete: Callable[[str], None] | None = None,
) -> None:
    """Schedule memory updates caused by a successful tool execution."""
    if not tool_result.get("success") or not tool_result.get("event_id"):
        return

    if schedule_upsert is None or schedule_delete is None:
        from app.memory.event_sync import (
            schedule_event_memory,
            schedule_event_memory_delete,
        )
        schedule_upsert = schedule_upsert or schedule_event_memory
        schedule_delete = schedule_delete or schedule_event_memory_delete

    if invocation.name in ("create_calendar_event", "update_calendar_event"):
        schedule_upsert(tool_result["event_id"])
    elif invocation.name == "delete_calendar_event":
        schedule_delete(tool_result["event_id"])
