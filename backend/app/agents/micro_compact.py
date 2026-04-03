"""micro_compact — 压缩旧的 tool_result 消息，节省上下文窗口。

在多轮工具循环中，每轮 LLM 调用前执行：
- 保留最近一轮的完整 tool_result（LLM 需要看到最新结果）
- 更早的 tool_result 压缩为简短摘要
"""

import json


def micro_compact(messages: list[dict], keep_recent: int = 1) -> None:
    """就地压缩 messages 中旧的 tool result。

    Args:
        messages: LLM 消息列表（会被原地修改）
        keep_recent: 保留最近 N 组 assistant+tool 的完整内容
    """
    # 找到所有 assistant 消息（带 tool_calls 的）的索引
    assistant_indices = [
        i for i, m in enumerate(messages)
        if m.get("role") == "assistant" and m.get("tool_calls")
    ]

    if len(assistant_indices) <= keep_recent:
        return  # 没有足够的历史轮次需要压缩

    # 只压缩 keep_recent 之前的轮次
    cutoff_idx = assistant_indices[-keep_recent]

    for i in range(cutoff_idx):
        msg = messages[i]
        if msg.get("role") != "tool":
            continue
        content = msg.get("content", "")
        if len(content) <= 200:
            continue  # 已经够短了

        # 尝试解析 JSON 并提取关键信息
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
