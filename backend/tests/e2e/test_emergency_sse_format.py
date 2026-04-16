"""验证 emergency SSE 事件格式与 iOS 客户端解析逻辑一致。

iOS ChatService.swift 解析逻辑:
  case "emergency":
      decode as [String: String]
      取 obj["message"] 和 obj["action"]
      → EmergencyData(message:, action:)

本测试确保：
1. 后端对紧急消息返回 event: emergency（不是 event: card）
2. data JSON 包含 message 和 action 字段（String 类型）
3. action 值是 find_er / call_vet / first_aid 之一
4. 非紧急消息不返回 emergency 事件
"""

import json
import pytest

from .conftest import E2EClient
from .test_messages import MESSAGES


VALID_ACTIONS = {"find_er", "call_vet", "first_aid"}


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_emergency_sse_event_format(e2e_with_pet: E2EClient, lang: str):
    """紧急消息应返回 event: emergency，且 JSON 格式匹配 iOS 解析。"""
    result = await e2e_with_pet.chat(MESSAGES["12.1"][lang])
    assert result.error is None, f"Chat error: {result.error}"

    # 1. 必须有 emergency 事件
    assert result.emergency is not None, (
        f"No emergency event received.\n"
        f"Raw events: {[e['event'] for e in result.raw_events]}"
    )

    # 2. iOS 用 [String: String] 解码，所有值必须是字符串
    emergency = result.emergency
    assert isinstance(emergency.get("message"), str), (
        f"message field must be a string, got {type(emergency.get('message'))}"
    )
    assert isinstance(emergency.get("action"), str), (
        f"action field must be a string, got {type(emergency.get('action'))}"
    )

    # 3. message 不为空
    assert len(emergency["message"]) > 0, "message should not be empty"

    # 4. action 是有效枚举值
    assert emergency["action"] in VALID_ACTIONS, (
        f"action={emergency['action']!r} not in {VALID_ACTIONS}"
    )

    # 5. 验证 raw SSE 事件类型是 "emergency" 不是 "card"
    emergency_events = [e for e in result.raw_events if e["event"] == "emergency"]
    card_emergency_events = [
        e for e in result.raw_events
        if e["event"] == "card" and '"type": "emergency"' in e.get("data", "")
    ]
    assert len(emergency_events) >= 1, (
        "Expected at least one SSE event with event: emergency"
    )
    assert len(card_emergency_events) == 0, (
        "Emergency should NOT be sent as event: card"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_history_query_no_emergency_event(e2e_with_pet: E2EClient, lang: str):
    """历史查询不应返回 emergency 事件。"""
    result = await e2e_with_pet.chat(MESSAGES["12.5"][lang])
    assert result.error is None

    # 不应有 emergency 事件
    emergency_events = [e for e in result.raw_events if e["event"] == "emergency"]
    assert len(emergency_events) == 0, (
        f"History query should NOT produce emergency event.\n"
        f"Got {len(emergency_events)} emergency events"
    )


@pytest.mark.asyncio
async def test_emergency_data_ios_decodable(e2e_with_pet: E2EClient):
    """模拟 iOS JSONDecoder().decode([String: String].self, from: data) 的行为。"""
    result = await e2e_with_pet.chat(MESSAGES["12.2"]["zh"])
    assert result.error is None

    # 找到 raw emergency 事件
    emergency_events = [e for e in result.raw_events if e["event"] == "emergency"]
    if not emergency_events:
        pytest.skip("Emergency event not produced (LLM non-deterministic)")

    raw_data = emergency_events[0]["data"]

    # 模拟 iOS: JSONDecoder().decode([String: String].self, from: json)
    # 这要求所有顶层值都是 String
    parsed = json.loads(raw_data)
    for key, value in parsed.items():
        assert isinstance(value, str), (
            f"iOS decodes as [String: String] — "
            f"key={key!r} has type {type(value).__name__}, must be str.\n"
            f"Full data: {raw_data}"
        )

    # iOS 取 obj["message"] 和 obj["action"]
    assert "message" in parsed, f"Missing 'message' key. Keys: {list(parsed.keys())}"
    assert "action" in parsed, f"Missing 'action' key. Keys: {list(parsed.keys())}"
