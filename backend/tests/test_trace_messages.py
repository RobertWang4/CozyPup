"""messages_for_trace: full prompt snapshot recorded on round 0 of every chat."""
import json

from app.debug.trace_logger import messages_for_trace


def test_plain_messages_pass_through_unchanged():
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    assert messages_for_trace(msgs) == msgs


def test_image_parts_are_replaced_with_placeholder():
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": "what is this"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + "A" * 5000}},
    ]}]
    out = messages_for_trace(msgs)
    assert out[0]["content"][0] == {"type": "text", "text": "what is this"}
    assert out[0]["content"][1] == {"type": "image_url", "image_url": "<omitted>"}
    assert "AAAA" not in json.dumps(out)


def test_oversized_payload_is_truncated_marker():
    msgs = [{"role": "system", "content": "x" * 300_000}]
    out = messages_for_trace(msgs, max_chars=200_000)
    assert out == {"_truncated": True, "_size": len(json.dumps(msgs, ensure_ascii=False)), "message_count": 1}


def test_tool_call_messages_are_kept():
    msgs = [{"role": "assistant", "content": None, "tool_calls": [{"id": "1", "function": {"name": "plan", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "1", "content": "ok"}]
    assert messages_for_trace(msgs) == msgs
