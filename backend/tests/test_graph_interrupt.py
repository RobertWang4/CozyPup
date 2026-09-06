"""Phase 2b — confirm cards via LangGraph `interrupt()` + a checkpointer.

The hard requirement is idempotency: LangGraph re-runs a node from the top
when a run resumes, so nothing may execute or be emitted twice across the
interrupt. These tests pin that, plus the SSE event order the iOS client
sees and the cancel path.
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agents import graph as graph_mod
from app.agents.checkpointer import RedactingSerializer, _redact_images, prune_checkpoints
from app.agents.graph import build_graph, stream_agent


def _tc(name, args, idx=0):
    return {
        "id": f"call_{idx}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }


def _fake_stream(rounds):
    async def _stream(messages, model, on_token, **kwargs):
        text, tool_calls = rounds[_stream.calls]
        _stream.calls += 1
        if text:
            on_token(text)
        return text, tool_calls, {"prompt_tokens": 10, "completion_tokens": 5}

    _stream.calls = 0
    return _stream


def _counting_dispatch(counts, *, confirm_tools=(), cards=None):
    """dispatch_tool stand-in that counts executions and emits a card each."""
    cards = cards or {}

    async def _dispatch(tool_call, db, user_id, session_id, result, on_card, lang, **kwargs):
        name = tool_call["function"]["name"]
        result.tools_called.add(name)
        if name in confirm_tools:
            card = {
                "type": "confirm_action",
                "action_id": kwargs.get("confirm_action_id", ""),
                "message": f"确认 {name}",
            }
            return {"status": "waiting_confirm", "executed": False, "_confirm_card": card}
        counts[name] = counts.get(name, 0) + 1
        result.tools_executed.add(name)
        card = cards.get(name, {"type": name, "n": counts[name]})
        result.cards.append(card)
        on_card(card)
        return {"success": True, "card": card}

    return _dispatch


def _config(thread_id):
    """The `configurable` the confirm endpoint rebuilds when it resumes."""
    return {
        "configurable": {
            "thread_id": thread_id,
            "db": None,
            "user_id": "u1",
            "session_id": "s1",
            "trace": graph_mod.INACTIVE_TRACE,
            "model": "m",
            "vision_model": "m",
            "images": None,
        },
    }


# ---------------------------------------------------------------------------
# Idempotency across interrupt / resume
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_confirm_tool_runs_once_across_interrupt_and_resume(monkeypatch):
    """[search_knowledge, delete_calendar_event]: search runs and emits once."""
    counts: dict[str, int] = {}
    monkeypatch.setattr(graph_mod, "_stream_completion", _fake_stream([
        ("我看看", [_tc("search_knowledge", {"query": "q"}, 0),
                    _tc("delete_calendar_event", {"event_id": "e1"}, 1)]),
    ]))
    monkeypatch.setattr(
        graph_mod, "dispatch_tool",
        _counting_dispatch(counts, confirm_tools=("delete_calendar_event",)),
    )

    graph = build_graph(InMemorySaver())
    sse = []
    result = None
    async for kind, payload in stream_agent(
        graph=graph, system_prompt="SYS",
        context_messages=[{"role": "user", "content": "删掉那条记录"}],
        db=None, user_id="u1", session_id="s1", thread_id="u1:corr-1",
    ):
        (sse if kind == "sse" else []).append(payload)
        if kind == "result":
            result = payload

    assert counts == {"search_knowledge": 1}
    assert len(result.confirm_cards) == 1
    assert result.confirm_cards[0]["action_id"] == "u1:corr-1"

    cards_before = [e["data"] for e in sse if e["event"] == "card"]
    assert [c["type"] for c in cards_before] == ["search_knowledge", "confirm_action"]

    # --- resume: the node re-runs from the top, nothing may fire twice ---
    executed = []

    async def _exec(invocation, context, **kwargs):
        executed.append(invocation.name)
        card = {"type": "record_deleted", "id": "e1"}
        context.result.tools_executed.add(invocation.name)
        context.result.cards.append(card)
        context.on_card(card)
        return {"success": True, "card": card}

    monkeypatch.setattr(graph_mod, "handle_tool_execution", _exec)

    config = _config("u1:corr-1")
    resumed = []
    async for mode, chunk in graph.astream(
        Command(resume=True), config, stream_mode=["custom", "updates"]
    ):
        if mode == "custom":
            resumed.append(chunk)

    assert counts == {"search_knowledge": 1}          # not re-executed
    assert executed == ["delete_calendar_event"]      # executed exactly once
    resumed_cards = [e["data"] for e in resumed if e["event"] == "card"]
    assert [c["type"] for c in resumed_cards] == ["record_deleted"]


@pytest.mark.asyncio
async def test_sse_event_order_across_confirm(monkeypatch):
    """thinking → confirm card … resume → the executed tool's card."""
    monkeypatch.setattr(graph_mod, "_stream_completion", _fake_stream([("", [
        _tc("delete_calendar_event", {"event_id": "e1"}, 0),
    ])]))

    async def _dispatch(tool_call, db, user_id, session_id, result, on_card, lang, **kwargs):
        graph_mod._emit_thinking("正在查找记录…", "delete_calendar_event")
        result.tools_called.add("delete_calendar_event")
        return {
            "status": "waiting_confirm",
            "executed": False,
            "_confirm_card": {
                "type": "confirm_action",
                "action_id": kwargs.get("confirm_action_id", ""),
                "message": "删除「洗澡」",
            },
        }

    monkeypatch.setattr(graph_mod, "dispatch_tool", _dispatch)

    graph = build_graph(InMemorySaver())
    sse = []
    async for kind, payload in stream_agent(
        graph=graph, system_prompt="SYS",
        context_messages=[{"role": "user", "content": "删掉洗澡"}],
        db=None, user_id="u1", session_id="s1", thread_id="u1:corr-2",
    ):
        if kind == "sse":
            sse.append(payload)

    assert [(e["event"], e["data"].get("type") or e["data"].get("tool")) for e in sse] == [
        ("thinking", "delete_calendar_event"),
        ("card", "confirm_action"),
    ]

    async def _exec(invocation, context, **kwargs):
        card = {"type": "record_deleted"}
        context.result.cards.append(card)
        context.on_card(card)
        return {"success": True, "card": card}

    monkeypatch.setattr(graph_mod, "handle_tool_execution", _exec)
    config = _config("u1:corr-2")
    after = [
        chunk async for mode, chunk in graph.astream(
            Command(resume=True), config, stream_mode=["custom", "updates"])
        if mode == "custom"
    ]
    assert [(e["event"], e["data"].get("type")) for e in after] == [("card", "record_deleted")]


@pytest.mark.asyncio
async def test_cancel_skips_the_tool(monkeypatch):
    """`Command(resume=False)` records a cancelled tool message, runs nothing."""
    monkeypatch.setattr(graph_mod, "_stream_completion", _fake_stream([("", [
        _tc("delete_pet", {"pet_id": "p1"}, 0),
    ])]))
    monkeypatch.setattr(
        graph_mod, "dispatch_tool", _counting_dispatch({}, confirm_tools=("delete_pet",)),
    )

    graph = build_graph(InMemorySaver())
    async for _ in stream_agent(
        graph=graph, system_prompt="SYS",
        context_messages=[{"role": "user", "content": "删掉三妹"}],
        db=None, user_id="u1", session_id="s1", thread_id="u1:corr-3",
    ):
        pass

    executed = []
    monkeypatch.setattr(
        graph_mod, "handle_tool_execution",
        lambda *a, **k: executed.append(1),
    )
    config = _config("u1:corr-3")
    async for _ in graph.astream(Command(resume=False), config, stream_mode=["custom", "updates"]):
        pass

    assert executed == []
    state = await graph.aget_state(config)
    tool_msg = [m for m in state.values["messages"] if m.get("role") == "tool"][-1]
    assert json.loads(tool_msg["content"]) == {"status": "cancelled", "executed": False}
    assert state.next == ()


# ---------------------------------------------------------------------------
# Serializer redaction
# ---------------------------------------------------------------------------

def test_redacting_serializer_strips_base64_images():
    payload = {
        "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": "看看这个"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + "A" * 5000}},
            ]},
            {"role": "assistant", "content": "好的"},
        ],
    }
    serde = RedactingSerializer()
    _, blob = serde.dumps_typed(payload)
    assert len(blob) < 500
    assert b"AAAA" not in blob

    restored = serde.loads_typed((_, blob))
    img = restored["messages"][0]["content"][1]["image_url"]["url"]
    assert img == "data:image/redacted"
    assert restored["messages"][1]["content"] == "好的"        # untouched


def test_redact_images_leaves_other_values_alone():
    obj = {"a": ["https://x/y.jpg", 1, None], "b": ("data:image/png;base64,zz",)}
    assert _redact_images(obj) == {
        "a": ["https://x/y.jpg", 1, None],
        "b": ("data:image/redacted",),
    }


# ---------------------------------------------------------------------------
# Prune
# ---------------------------------------------------------------------------

class _FakeCursor:
    def __init__(self, rows, log):
        self._rows, self.log = rows, log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        self.log.append((" ".join(sql.split()), params))

    async def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self.log = []
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows, self.log)


@pytest.mark.asyncio
async def test_prune_checkpoints_deletes_all_three_tables():
    conn = _FakeConn([("t1",), ("t2",)])
    deleted = await prune_checkpoints(timedelta(days=7), conn=conn)

    assert deleted == 2
    select_sql, select_params = conn.log[0]
    assert "GROUP BY thread_id" in select_sql
    cutoff = datetime.fromisoformat(select_params[0])
    assert timedelta(days=6, hours=23) < datetime.now(timezone.utc) - cutoff < timedelta(days=7, minutes=1)

    deletes = [(sql, params) for sql, params in conn.log[1:]]
    assert [sql for sql, _ in deletes] == [
        "DELETE FROM checkpoint_writes WHERE thread_id = ANY(%s)",
        "DELETE FROM checkpoint_blobs WHERE thread_id = ANY(%s)",
        "DELETE FROM checkpoints WHERE thread_id = ANY(%s)",
    ]
    assert all(params == (["t1", "t2"],) for _, params in deletes)


@pytest.mark.asyncio
async def test_prune_checkpoints_noop_when_nothing_stale():
    conn = _FakeConn([])
    assert await prune_checkpoints(timedelta(days=7), conn=conn) == 0
    assert len(conn.log) == 1      # only the SELECT


# ---------------------------------------------------------------------------
# Confirm endpoint helpers
# ---------------------------------------------------------------------------

def test_checkpoint_freshness_window():
    from app.routers.chat import _checkpoint_is_fresh

    now = datetime.now(timezone.utc)
    assert _checkpoint_is_fresh(SimpleNamespace(created_at=now.isoformat()))
    assert not _checkpoint_is_fresh(
        SimpleNamespace(created_at=(now - timedelta(hours=2)).isoformat())
    )
    assert not _checkpoint_is_fresh(SimpleNamespace(created_at=None))
    assert not _checkpoint_is_fresh(SimpleNamespace(created_at="not-a-date"))
