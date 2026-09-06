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
        _stream.seen.append([dict(m) for m in messages])
        text, tool_calls = rounds[_stream.calls]
        _stream.calls += 1
        if text:
            on_token(text)
        return text, tool_calls, {"prompt_tokens": 10, "completion_tokens": 5}

    _stream.calls = 0
    _stream.seen = []          # messages handed to the LLM, per round
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
        ("找到了，请点确认～", []),
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
    # The confirm card lands at the END of the turn, after the extra model
    # round's text — not immediately after the tools node.
    assert sse[-1]["event"] == "card" and sse[-1]["data"]["type"] == "confirm_action"
    assert result.response_text == "我看看找到了，请点确认～"

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
    """thinking → confirm card … resume → the executed tool's card.

    The model stays silent in both rounds, so the fixed-prompt safety net in
    `stream_agent` supplies the reply text.
    """
    monkeypatch.setattr(graph_mod, "_stream_completion", _fake_stream([
        ("", [_tc("delete_calendar_event", {"event_id": "e1"}, 0)]),
        ("", []),
    ]))

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
    sse, result = [], None
    async for kind, payload in stream_agent(
        graph=graph, system_prompt="SYS",
        context_messages=[{"role": "user", "content": "删掉洗澡"}],
        db=None, user_id="u1", session_id="s1", thread_id="u1:corr-2",
    ):
        if kind == "sse":
            sse.append(payload)
        else:
            result = payload

    # The model said nothing in either round, so a fixed "tap the card" line
    # is streamed ahead of the card and becomes the saved reply text.
    assert [(e["event"], e["data"].get("type") or e["data"].get("tool") or e["data"].get("text")) for e in sse] == [
        ("thinking", "delete_calendar_event"),
        ("token", "请在上方卡片点「确认」，我再帮你执行～"),
        ("card", "confirm_action"),
    ]
    assert result.response_text == "请在上方卡片点「确认」，我再帮你执行～"

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
    """`Command(resume=False)` runs nothing and finishes the graph."""
    monkeypatch.setattr(graph_mod, "_stream_completion", _fake_stream([
        ("", [_tc("delete_pet", {"pet_id": "p1"}, 0)]),
        ("请点确认", []),
    ]))
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
    tool_msgs = [m for m in state.values["messages"] if m.get("role") == "tool"]
    # `tools` already answered call_0 with waiting_confirm; the cancel path
    # must not append a second message for the same tool_call_id.
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_0"
    assert json.loads(tool_msgs[0]["content"])["status"] == "waiting_confirm"
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


def test_make_pool_constructs_without_connecting():
    # psycopg's default min_size (4) exceeds our max_size (3); the pool must
    # be constructible with open=False — this caught a startup failure on the
    # real DB that mocked tests missed.
    from app.agents.checkpointer import make_pool

    pool = make_pool()
    assert pool.min_size == 1 and pool.max_size == 3


@pytest.mark.asyncio
async def test_interrupt_keeps_model_text_when_present(monkeypatch):
    """If the model spoke before the confirmable call, no synthetic prompt is added."""
    monkeypatch.setattr(graph_mod, "_stream_completion", _fake_stream([
        ("好的，这就帮你删～", [_tc("delete_calendar_event", {"event_id": "e1"}, 0)]),
        ("", []),
    ]))
    monkeypatch.setattr(
        graph_mod, "dispatch_tool", _counting_dispatch({}, confirm_tools=("delete_calendar_event",)),
    )
    graph = build_graph(InMemorySaver())
    sse, result = [], None
    async for kind, payload in stream_agent(
        graph=graph, system_prompt="SYS",
        context_messages=[{"role": "user", "content": "删掉洗澡"}],
        db=None, user_id="u1", session_id="s1", thread_id="u1:corr-text",
    ):
        if kind == "sse":
            sse.append(payload)
        else:
            result = payload
    assert [e["event"] for e in sse] == ["token", "card"]
    assert result.response_text == "好的，这就帮你删～"


# ---------------------------------------------------------------------------
# Interrupt at the END of the turn (regression: the model used to never see
# the other tools' results, so the care advice / chat reply was dropped)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deferred_call_still_gets_a_second_model_round(monkeypatch):
    """[search_knowledge, create_calendar_event(confirm)] → model round 2 runs.

    Round 2 must see the search result AND a `waiting_confirm` tool message
    for the deferred call, its text must reach `response_text`, and the
    confirm card must be the last SSE event of the turn.
    """
    counts: dict[str, int] = {}
    stream = _fake_stream([
        ("我查一下资料。", [
            _tc("search_knowledge", {"query": "猫呕吐"}, 0),
            _tc("create_calendar_event", {"title": "呕吐"}, 1),
        ]),
        ("轻微呕吐先禁食 4 小时，观察精神状态。记录卡片请点确认～", []),
    ])
    monkeypatch.setattr(graph_mod, "_stream_completion", stream)
    monkeypatch.setattr(
        graph_mod, "dispatch_tool",
        _counting_dispatch(
            counts,
            confirm_tools=("create_calendar_event",),
            cards={"search_knowledge": {"type": "references", "n": 1}},
        ),
    )

    finalized = []
    real_finalize = graph_mod.finalize_node

    def _spy_finalize(state, config):
        finalized.append(1)
        return real_finalize(state, config)

    monkeypatch.setattr(graph_mod, "finalize_node", _spy_finalize)

    graph = build_graph(InMemorySaver())
    sse, result = [], None
    async for kind, payload in stream_agent(
        graph=graph, system_prompt="SYS",
        context_messages=[{"role": "user", "content": "猫吐了一次，帮我记一下"}],
        db=None, user_id="u1", session_id="s1", thread_id="u1:corr-adv",
    ):
        if kind == "sse":
            sse.append(payload)
        else:
            result = payload

    # --- the second model round happened and saw both results ---
    assert stream.calls == 2
    round2 = stream.seen[1]
    tool_msgs = {m["tool_call_id"]: json.loads(m["content"])
                 for m in round2 if m.get("role") == "tool"}
    assert tool_msgs["call_0"]["success"] is True                  # search result
    assert tool_msgs["call_1"]["status"] == "waiting_confirm"      # deferred call
    assert tool_msgs["call_1"]["executed"] is False
    assert tool_msgs["call_1"]["description"] == "确认 create_calendar_event"

    # --- round 2's advice survives into the saved reply ---
    assert "禁食 4 小时" in result.response_text
    assert result.response_text.startswith("我查一下资料。")

    # --- the confirm card is the LAST event of the turn ---
    assert sse[-1]["event"] == "card"
    assert sse[-1]["data"]["type"] == "confirm_action"
    assert [e["data"]["type"] for e in sse if e["event"] == "card"] == [
        "references", "confirm_action",
    ]
    assert counts == {"search_knowledge": 1}
    assert finalized == []          # finalize waits for the resume

    # --- resume: tool executed once, card emitted once, finalize runs once ---
    executed = []

    async def _exec(invocation, context, **kwargs):
        executed.append(invocation.name)
        card = {"type": "record", "id": "e1"}
        context.result.tools_executed.add(invocation.name)
        context.result.cards.append(card)
        context.on_card(card)
        return {"success": True, "card": card}

    monkeypatch.setattr(graph_mod, "handle_tool_execution", _exec)

    config = _config("u1:corr-adv")
    resumed = [
        chunk async for mode, chunk in graph.astream(
            Command(resume=True), config, stream_mode=["custom", "updates"])
        if mode == "custom"
    ]

    assert executed == ["create_calendar_event"]
    assert stream.calls == 2                                # no extra LLM round
    assert [e["data"]["type"] for e in resumed if e["event"] == "card"] == ["record"]
    assert finalized == [1]

    state = await graph.aget_state(config)
    assert state.next == ()
    # finalize kept the pre-interrupt text and added no cards of its own
    assert "禁食 4 小时" in state.values["response_text"]
    assert [c["type"] for c in state.values["cards"]] == ["references", "record"]
    # one tool message per tool_call_id — no duplicate for the confirmed call
    ids = [m["tool_call_id"] for m in state.values["messages"] if m.get("role") == "tool"]
    assert ids == ["call_0", "call_1"]


@pytest.mark.asyncio
async def test_confirm_card_last_when_round2_only_talks(monkeypatch):
    """Round 2 calls no tools: its text streams first, the card comes last."""
    monkeypatch.setattr(graph_mod, "_stream_completion", _fake_stream([
        ("", [_tc("delete_calendar_event", {"event_id": "e1"}, 0)]),
        ("这条记录我准备好了，点卡片确认我就删～", []),
    ]))
    monkeypatch.setattr(
        graph_mod, "dispatch_tool",
        _counting_dispatch({}, confirm_tools=("delete_calendar_event",)),
    )

    graph = build_graph(InMemorySaver())
    sse, result = [], None
    async for kind, payload in stream_agent(
        graph=graph, system_prompt="SYS",
        context_messages=[{"role": "user", "content": "删掉洗澡"}],
        db=None, user_id="u1", session_id="s1", thread_id="u1:corr-talk",
    ):
        if kind == "sse":
            sse.append(payload)
        else:
            result = payload

    assert [e["event"] for e in sse] == ["token", "card"]
    assert sse[0]["data"]["text"] == "这条记录我准备好了，点卡片确认我就删～"
    assert sse[1]["data"]["type"] == "confirm_action"
    assert result.response_text == "这条记录我准备好了，点卡片确认我就删～"


@pytest.mark.asyncio
async def test_deferred_confirm_survives_the_round_cap(monkeypatch):
    """Deferred call parked in round 0, MAX_ROUNDS hit: still interrupts."""
    from app.agents.orchestrator import MAX_ROUNDS

    counts: dict[str, int] = {}
    rounds = [("回合0", [_tc("delete_pet", {"pet_id": "p1"}, 0)])]
    rounds += [
        (f"回合{i}", [_tc("search_knowledge", {"query": str(i)}, i)])
        for i in range(1, MAX_ROUNDS)
    ]
    stream = _fake_stream(rounds)
    monkeypatch.setattr(graph_mod, "_stream_completion", stream)
    monkeypatch.setattr(
        graph_mod, "dispatch_tool", _counting_dispatch(counts, confirm_tools=("delete_pet",)),
    )

    graph = build_graph(InMemorySaver())
    sse, result = [], None
    async for kind, payload in stream_agent(
        graph=graph, system_prompt="SYS",
        context_messages=[{"role": "user", "content": "删掉三妹"}],
        db=None, user_id="u1", session_id="s1", thread_id="u1:corr-cap",
    ):
        if kind == "sse":
            sse.append(payload)
        else:
            result = payload

    assert stream.calls == MAX_ROUNDS          # the cap, not one more
    assert counts == {"search_knowledge": MAX_ROUNDS - 1}
    assert sse[-1]["event"] == "card"
    assert sse[-1]["data"]["type"] == "confirm_action"
    assert len(result.confirm_cards) == 1
    state = await graph.aget_state(_config("u1:corr-cap"))
    assert state.next == ("confirm",)
