"""Typed parsing for raw LLM tool calls."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolInvocation:
    id: str
    name: str
    arguments: dict[str, Any]


def parse_tool_invocation(tool_call: dict) -> ToolInvocation:
    """Parse one raw LiteLLM tool call into a typed invocation."""
    fn = tool_call["function"]
    try:
        arguments = json.loads(fn["arguments"])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON arguments: {exc}") from exc
    return ToolInvocation(
        id=tool_call.get("id", ""),
        name=fn["name"],
        arguments=arguments,
    )
