"""Phase 2a — serializable AgentState.

Two things are pinned here:

1. The message list handed to the LLM each round is byte-identical to what
   the Phase 1 (in-place-mutation) graph produced. `messages` is now an
   append-only reducer field, so every node returns only its delta.
2. Every `updates` chunk the graph emits — and the accumulated state — is
   checkpointable with the serializer Phase 2b will use.
"""

import copy
import json

import pytest

from app.agents import graph as graph_mod
from app.agents.graph import stream_agent


def _tc(name, args, idx=0):
    return {
        "id": f"call_{idx}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }


def _fake_stream(rounds):
    """Fake `_stream_completion` replaying `rounds` = [(text, tool_calls), ...]."""
    seen = []

    async def _stream(messages, model, on_token, **kwargs):
        seen.append(copy.deepcopy(messages))
        text, tool_calls = rounds[len(seen) - 1]
        if text:
            on_token(text)
        return text, tool_calls, {"prompt_tokens": 10, "completion_tokens": 5}

    return _stream, seen


def _fake_dispatch(results):
    """Fake `dispatch_tool` returning `results[tool_name]`."""

    async def _dispatch(tool_call, db, user_id, session_id, result, on_card, lang, **kwargs):
        name = tool_call["function"]["name"]
        result.tools_called.add(name)
        out = copy.deepcopy(results.get(name, {"success": True}))
        if out.get("success"):
            result.tools_executed.add(name)
        if isinstance(out.get("card"), dict):
            result.cards.append(out["card"])
        if name == "plan":
            result.plan_steps = json.loads(tool_call["function"]["arguments"])["steps"]
        return out

    return _dispatch


async def _run(monkeypatch, rounds, tool_results=None, **kwargs):
    """Drive the graph with fakes; return (prompts_per_round, updates, result)."""
    stream, seen = _fake_stream(rounds)
    monkeypatch.setattr(graph_mod, "_stream_completion", stream)
    monkeypatch.setattr(graph_mod, "dispatch_tool", _fake_dispatch(tool_results or {}))

    updates = []
    real_astream = graph_mod.get_graph().astream

    async def spy_astream(initial, config, **kw):
        async for mode, chunk in real_astream(initial, config, **kw):
            if mode != "custom":
                updates.append(chunk)
            yield mode, chunk

    class _G:
        astream = staticmethod(spy_astream)

    result = None
    async for kind, payload in stream_agent(
        graph=_G(),
        system_prompt="SYS",
        context_messages=[{"role": "user", "content": "hi"}],
        db=None,
        user_id="u1",
        **kwargs,
    ):
        if kind == "result":
            result = payload
    return seen, updates, result


# ---------------------------------------------------------------------------
# 1. Prompt byte-identity with the Phase 1 graph
# ---------------------------------------------------------------------------

SYS = {"role": "system", "content": "SYS"}
USER = {"role": "user", "content": "hi"}


@pytest.mark.asyncio
async def test_prompt_plain_chat(monkeypatch):
    seen, _, result = await _run(monkeypatch, [("你好", [])])
    assert seen == [[SYS, USER]]
    assert result.response_text == "你好"


@pytest.mark.asyncio
async def test_prompt_two_round_tool_run(monkeypatch):
    call = _tc("query_calendar_events", {"pet_id": "p1"})
    seen, _, result = await _run(
        monkeypatch,
        [("", [call]), ("查到了", [])],
        {"query_calendar_events": {"success": True, "events": []}},
    )
    assert seen[0] == [SYS, USER]
    assert seen[1] == [
        SYS,
        USER,
        {"role": "assistant", "content": None, "tool_calls": [call]},
        {
            "role": "tool",
            "tool_call_id": "call_0",
            "content": json.dumps({"success": True, "events": []}, ensure_ascii=False),
        },
    ]
    assert result.response_text == "查到了"


@pytest.mark.asyncio
async def test_prompt_micro_compact_matches_in_place(monkeypatch):
    """3 tool rounds: round 2's prompt must show round 0's result compacted."""
    big = {"success": True, "card": {"type": "events"}, "blob": "x" * 500}
    c0 = _tc("query_calendar_events", {"n": 0})
    c1 = _tc("list_reminders", {"n": 1})
    seen, _, _ = await _run(
        monkeypatch,
        [("", [c0]), ("", [c1]), ("好了", [])],
        {"query_calendar_events": big, "list_reminders": big},
    )
    full = json.dumps(big, ensure_ascii=False)
    compact = json.dumps({"success": True, "card_type": "events"}, ensure_ascii=False)
    # Round 1 sees round 0's result in full (keep_recent=1).
    assert seen[1][3]["content"] == full
    # Round 2: round 0 compacted, round 1 still full.
    assert seen[2][3]["content"] == compact
    assert seen[2][5]["content"] == full


@pytest.mark.asyncio
async def test_prompt_nudge_retry(monkeypatch):
    from app.agents.pre_processing.types import SuggestedAction

    args = {"query": "宠物医院"}
    seen, _, _ = await _run(
        monkeypatch,
        [("附近有医院哦", []), ("找到了", [])],
        suggested_actions=[
            SuggestedAction(tool_name="search_places", arguments=args, confidence=0.9)
        ],
    )
    assert seen[0] == [SYS, USER]
    assert seen[1] == [
        SYS,
        USER,
        {"role": "assistant", "content": "附近有医院哦"},
        {
            "role": "user",
            "content": (
                "你的回复没有调用工具。根据用户意图分析，你应该调用以下工具：\n"
                f"- search_places({json.dumps(args, ensure_ascii=False)})"
                "\n请立即调用对应的工具。不要用文字假装操作已完成。"
            ),
        },
    ]


@pytest.mark.asyncio
async def test_prompt_write_claim_nag(monkeypatch):
    seen, _, _ = await _run(monkeypatch, [("已删除啦", []), ("抱歉", [])])
    assert seen[0] == [SYS, USER]
    assert len(seen[1]) == 4
    assert seen[1][:2] == [SYS, USER]
    assert seen[1][2] == {"role": "assistant", "content": "已删除啦"}
    assert seen[1][3]["role"] == "user"
    assert seen[1][3]["content"].startswith("⚠️ 严重错误：")


@pytest.mark.asyncio
async def test_prompt_plan_nag(monkeypatch):
    steps = [{"id": 1, "action": "记录", "tool": "create_calendar_event"}]
    plan_call = _tc("plan", {"steps": steps})
    seen, _, _ = await _run(
        monkeypatch,
        [("", [plan_call]), ("好的", []), ("嗯嗯", [])],
        {"plan": {"success": True}},
    )
    assert seen[1][2] == {"role": "assistant", "content": None, "tool_calls": [plan_call]}
    assert seen[2][:4] == seen[1]
    assert seen[2][4] == {"role": "assistant", "content": "好的"}
    assert seen[2][5] == {
        "role": "user",
        "content": (
            "你的 plan 还有未完成的步骤:\n"
            "- [1] 记录 → create_calendar_event\n"
            "请立即调用对应的工具完成这些步骤。"
        ),
    }


@pytest.mark.asyncio
async def test_prompt_request_images_injection(monkeypatch):
    call = _tc("request_images", {})
    seen, _, _ = await _run(
        monkeypatch,
        [("", [call]), ("看到了", [])],
        {"request_images": {"success": True, "_inject_images": ["QUJD"]}},
        images=["QUJD"],
    )
    assert seen[1][-1] == {
        "role": "user",
        "content": [
            {"type": "text", "text": "这是用户附带的图片，请仔细查看后回答："},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}},
        ],
    }
    # The internal `_inject_images` marker never reaches the LLM.
    assert "_inject_images" not in seen[1][3]["content"]


@pytest.mark.asyncio
async def test_prompt_pushback_preamble(monkeypatch):
    stream, seen = _fake_stream([("好的", [])])
    monkeypatch.setattr(graph_mod, "_stream_completion", stream)
    async for _ in stream_agent(
        system_prompt="SYS",
        context_messages=[{"role": "user", "content": "你没删啊"}],
        db=None,
        user_id="u1",
    ):
        pass
    assert [m["role"] for m in seen[0]] == ["system", "user", "system"]
    assert seen[0][2]["content"].startswith("⚠️【系统强制指令")
# ---------------------------------------------------------------------------
# 2. Serializability
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_updates_are_checkpointable(monkeypatch):
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    call = _tc("create_calendar_event", {"pet_id": "p1", "title": "吃狗粮"})
    seen, updates, result = await _run(
        monkeypatch,
        [("", [call]), ("已记录", [])],
        {"create_calendar_event": {"success": True, "card": {"type": "record"}}},
        pets=[{"id": "p1", "name": "小黑", "species": "dog"}],
        location={"lat": 1.0, "lng": 2.0},
        images=["QUJD"],
    )
    assert updates, "expected `updates` chunks"

    serde = JsonPlusSerializer()
    accumulated: dict = {}
    for chunk in updates:
        serde.dumps_typed(chunk)
        for node_update in chunk.values():
            if isinstance(node_update, dict):
                accumulated.update(node_update)
    serde.dumps_typed(accumulated)

    # No base64 leaked into state (it lives in config["configurable"]).
    assert "images" not in accumulated
    assert result.cards == [{"type": "record"}]


@pytest.mark.asyncio
async def test_non_node_update_chunks_are_ignored(monkeypatch):
    """An `__interrupt__` chunk must not crash the accumulator (Phase 2b)."""
    stream, _ = _fake_stream([("你好", [])])
    monkeypatch.setattr(graph_mod, "_stream_completion", stream)
    real_astream = graph_mod.get_graph().astream

    async def spy_astream(initial, config, **kw):
        yield "updates", {"__interrupt__": ("not-a-dict",)}
        async for item in real_astream(initial, config, **kw):
            yield item

    class _G:
        astream = staticmethod(spy_astream)

    result = None
    async for kind, payload in stream_agent(
        graph=_G(),
        system_prompt="SYS",
        context_messages=[USER],
        db=None,
        user_id="u1",
    ):
        if kind == "result":
            result = payload
    assert result.response_text == "你好"
