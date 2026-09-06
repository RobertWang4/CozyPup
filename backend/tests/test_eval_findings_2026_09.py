"""Regression tests for bugs surfaced by the 2026-09-03 harness eval.

See tests/e2e/reports/eval_trace_2026-09-03.md for the traces.
"""
import asyncio
import inspect
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.orchestrator import _can_skip_round2, _text_claims_write, OrchestratorResult
from app.agents.pre_processing import pre_process
from app.agents.tool_context import ToolDispatchContext
from app.agents.tool_execution import handle_tool_execution
from app.agents.tool_invocation import ToolInvocation
from app.agents.tools.registry import get_registered_tools
from app.memory.context_builder import build_memory_context
from app.routers.chat import _user_today


# 1. memory retrieval must never touch the request session --------------------
#
# 2026-09-06: the earlier fix rolled back the shared session on timeout. A
# rollback expires every loaded ORM object, so building the system prompt
# right after it raised MissingGreenlet on `pet.name`. Retrieval now runs on
# its own session; the request session is neither used nor rolled back.

class _FakeSessionFactory:
    def __init__(self):
        self.sessions = []

    def __call__(self):
        session = AsyncMock()
        self.sessions.append(session)
        return session


@pytest.mark.asyncio
async def test_memory_timeout_leaves_request_session_alone():
    db = AsyncMock()
    factory = _FakeSessionFactory()
    seen = []

    async def slow_retrieve(**kwargs):
        seen.append(kwargs["db"])
        await asyncio.sleep(1)

    await build_memory_context(
        message="hi", db=db, user_id="u", retrieve=slow_retrieve, timeout_ms=10,
        session_factory=factory,
    )
    db.rollback.assert_not_awaited()
    assert seen and seen[0] is not db
    assert seen[0] is factory.sessions[0].__aenter__.return_value


@pytest.mark.asyncio
async def test_memory_error_leaves_request_session_alone():
    db = AsyncMock()

    async def bad_retrieve(**kwargs):
        raise RuntimeError("boom")

    await build_memory_context(
        message="hi", db=db, user_id="u", retrieve=bad_retrieve,
        session_factory=_FakeSessionFactory(),
    )
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_exception_rolls_back_session():
    db = AsyncMock()
    execute = AsyncMock(side_effect=RuntimeError("boom"))
    result = await handle_tool_execution(
        ToolInvocation(id="c", name="query_calendar_events", arguments={}),
        ToolDispatchContext(db=db),
        validate=lambda n, a: [],
        execute=execute,
    )
    assert "error" in result
    db.rollback.assert_awaited_once()


# 2. every registered handler must accept (arguments, db, user_id) -----------

def test_all_registered_handlers_accept_standard_positional_args():
    for name, entry in get_registered_tools().items():
        sig = inspect.signature(entry["handler"])
        positional = [
            p for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        has_var = any(p.kind == p.VAR_POSITIONAL for p in sig.parameters.values())
        assert len(positional) >= 3 or has_var, f"{name} handler signature {sig}"


# 3. write-claim guard must ignore negated / passive mentions ---------------

@pytest.mark.parametrize("text", [
    "I checked, but no events at all were recorded for Max today.",
    "There is no vomiting record on file — nothing was deleted.",
    "I haven't updated anything yet.",
    "我查了一下，今天没有记录，也没有删除任何东西。",
])
def test_write_claim_ignores_negations(text):
    lang = "zh" if any("一" <= c <= "鿿" for c in text) else "en"
    assert not _text_claims_write(text, lang)


@pytest.mark.parametrize("text,lang", [
    ("Done — I've deleted the vomiting record.", "en"),
    ("已删除豆豆的呕吐记录。", "zh"),
])
def test_write_claim_still_catches_real_claims(text, lang):
    assert _text_claims_write(text, lang)


# 4. skip_round2 must not fire when a tool was deferred behind a confirm card

def test_skip_round2_blocked_by_waiting_confirm():
    tool_calls = [{"function": {"name": "create_calendar_event"}}]
    results = {"create_calendar_event": {"status": "waiting_confirm", "executed": False}}
    assert not _can_skip_round2(tool_calls, results, OrchestratorResult(), "I'll jot that down, then give guidance.")


def test_skip_round2_still_fires_on_success():
    tool_calls = [{"function": {"name": "create_calendar_event"}}]
    results = {"create_calendar_event": {"success": True, "card": {"type": "record"}}}
    assert _can_skip_round2(tool_calls, results, OrchestratorResult(), "正在记录…")


# 5. pre-processor must not suggest create for delete/update sentences ------

@pytest.mark.parametrize("message", [
    "把豆豆今天的呕吐记录删掉",
    "Delete Max's vomiting record from today.",
    "豆豆昨天的呕吐记录删了吧",
    "remove the vomit entry",
])
def test_preprocessor_ignores_delete_sentences(message):
    pet = SimpleNamespace(id="p1", name="豆豆" if "豆豆" in message else "Max")
    actions = pre_process(message, [pet], today=date(2026, 9, 3), lang="zh")
    assert not any(a.tool_name == "create_calendar_event" for a in actions)


def test_preprocessor_still_suggests_plain_record():
    pet = SimpleNamespace(id="p1", name="豆豆")
    actions = pre_process("豆豆今天吐了两次", [pet], today=date(2026, 9, 3), lang="zh")
    assert any(a.tool_name == "create_calendar_event" for a in actions)


# 6. "today" must follow the user's timezone ---------------------------------

def test_user_today_uses_timezone():
    from datetime import datetime, timezone
    now = datetime(2026, 9, 3, 4, 10, tzinfo=timezone.utc)  # 21:10 PDT on Sep 2
    assert _user_today("America/Los_Angeles", now=now) == date(2026, 9, 2)
    assert _user_today("Asia/Shanghai", now=now) == date(2026, 9, 3)
    assert _user_today(None, now=now) == date(2026, 9, 3)
    assert _user_today("Not/AZone", now=now) == date(2026, 9, 3)
