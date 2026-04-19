"""micro_compact — compress old tool_result payloads to save prompt tokens.

Called between rounds in `orchestrator.run_orchestrator`. The most recent
round's results stay intact (the LLM needs them to decide what to do
next), but earlier rounds' verbose results get replaced with a minimal
summary (success / error / status / card_type).

For a 5-round session with large query results this can save thousands
of tokens per request.
"""

import json


def micro_compact(messages: list[dict], keep_recent: int = 1) -> None:
    """Compress old tool-result messages in place.

    Args:
        messages: LLM message list (mutated in place).
        keep_recent: Keep the last N assistant+tool round groups intact.
    """
    # Locate the assistant turns that triggered tool calls — those bracket
    # each "round group" of (assistant tool_calls → tool results).
    assistant_indices = [
        i for i, m in enumerate(messages)
        if m.get("role") == "assistant" and m.get("tool_calls")
    ]

    if len(assistant_indices) <= keep_recent:
        return  # Not enough history to compress yet

    # Compress everything before the kept recent round(s)
    cutoff_idx = assistant_indices[-keep_recent]

    for i in range(cutoff_idx):
        msg = messages[i]
        if msg.get("role") != "tool":
            continue
        content = msg.get("content", "")
        if len(content) <= 200:
            continue  # Already small enough — don't waste cycles

        # Try to keep structurally-meaningful bits; fall back to truncation.
        try:
            data = json.loads(content)
            summary = {}
            if "success" in data:
                summary["success"] = data["success"]
            if "error" in data:
                summary["error"] = str(data["error"])[:100]
            if "status" in data:
                summary["status"] = data["status"]
            if "card" in data and isinstance(data["card"], dict):
                summary["card_type"] = data["card"].get("type", "unknown")
            if not summary:
                summary["compressed"] = True
            msg["content"] = json.dumps(summary, ensure_ascii=False)
        except (json.JSONDecodeError, AttributeError):
            msg["content"] = content[:200] + "…"
