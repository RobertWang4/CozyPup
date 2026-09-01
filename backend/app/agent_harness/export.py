"""Export harness traces into training-data friendly rows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .trace_schema import TraceArtifact


def _tool_dispatch_steps(artifact: TraceArtifact) -> list[dict[str, Any]]:
    steps = artifact.raw_trace.get("steps", [])
    return [
        step.get("data", {})
        for step in steps
        if step.get("step") == "tool_dispatch" and isinstance(step.get("data"), dict)
    ]


def _json_args(raw_args) -> str:
    if isinstance(raw_args, str):
        return raw_args
    return json.dumps(raw_args or {}, ensure_ascii=False)


def trace_to_sft_row(artifact: TraceArtifact, *, success: bool) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": message}
        for message in artifact.input_messages
    ]

    tool_calls = []
    for index, data in enumerate(_tool_dispatch_steps(artifact)):
        tool_name = data.get("tool")
        if not tool_name:
            continue
        call_id = f"call_{index}"
        tool_calls.append({
            "id": call_id,
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": _json_args(data.get("args")),
            },
        })
        messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "name": tool_name,
            "content": json.dumps({"success": bool(data.get("success"))}, ensure_ascii=False),
        })

    if tool_calls:
        messages.insert(len(artifact.input_messages), {
            "role": "assistant",
            "tool_calls": tool_calls,
        })

    messages.append({"role": "assistant", "content": artifact.output_text})

    return {
        "messages": messages,
        "metadata": {
            "scenario": artifact.scenario_id,
            "tools_called": artifact.tools_called,
            "success": success,
            "elapsed_ms": artifact.elapsed_ms,
            "total_tokens": artifact.total_tokens,
        },
    }


def append_sft_jsonl(path: str | Path, row: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
