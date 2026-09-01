"""Human-readable rendering for agent harness results."""

from __future__ import annotations

import json

from .client import ChatResult, get_tools_called


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def render_result(result: ChatResult, *, verbose: bool = False) -> str:
    """Render a chat result for terminal debugging."""
    lines: list[str] = []
    lines.append(f"RESPONSE ({result.elapsed_ms}ms)")
    lines.append(result.text.strip() or "(empty)")

    if result.error:
        lines.extend(["", "ERROR", result.error])

    if result.emergency:
        lines.extend(["", "EMERGENCY", _json(result.emergency)])

    lines.append("")
    lines.append(f"CARDS ({len(result.cards)})")
    if result.cards:
        for i, card in enumerate(result.cards, 1):
            summary = card.get("type", "card")
            lines.append(f"[{i}] {summary}")
            lines.append(_json(card))
    else:
        lines.append("(none)")

    tools = get_tools_called(result)
    lines.extend(["", "TOOLS", ", ".join(tools) if tools else "(none)"])

    if result.session_id:
        lines.extend(["", "SESSION", result.session_id])

    if verbose and result.trace:
        prompt = result.trace.get("total_prompt_tokens", 0)
        completion = result.trace.get("total_completion_tokens", 0)
        total = result.trace.get("total_tokens", prompt + completion)
        lines.extend(["", "TRACE", f"tokens: prompt={prompt} completion={completion} total={total}"])

        for step in result.trace.get("steps", []):
            if not isinstance(step, dict):
                continue
            elapsed = step.get("elapsed_ms", "?")
            name = step.get("step", "?")
            lines.append(f"[{elapsed}ms] {name}")
            if "data" in step:
                data = step["data"]
                if isinstance(data, (dict, list)):
                    lines.append(_json(data))
                else:
                    lines.append(str(data))

        events = result.trace.get("events") or []
        if events:
            lines.append("")
            lines.append(f"EVENTS ({len(events)})")
            for event in events:
                if not isinstance(event, dict):
                    continue
                elapsed = event.get("elapsed_ms", "?")
                name = event.get("type", "?")
                lines.append(f"[{elapsed}ms] {name}")
                if "data" in event:
                    lines.append(_json(event["data"]))

        rounds = result.trace.get("llm_rounds") or []
        if rounds:
            lines.append("")
            lines.append(f"LLM ROUNDS ({len(rounds)})")
            for item in rounds:
                if not isinstance(item, dict):
                    continue
                lines.append(f"round={item.get('round')} elapsed={item.get('elapsed_ms')}ms")

    return "\n".join(lines)
