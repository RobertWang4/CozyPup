from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.agents.tool_context import ToolDispatchContext
from app.agents.tool_execution import handle_tool_execution
from app.agents.tool_invocation import ToolInvocation


@pytest.mark.asyncio
async def test_validation_error_returns_error_without_execute():
    execute = AsyncMock()

    result = await handle_tool_execution(
        ToolInvocation(id="call-1", name="create_pet", arguments={}),
        ToolDispatchContext(),
        validate=lambda name, args: ["missing name"],
        execute=execute,
    )

    assert result == {"error": "missing name"}
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_success_executes_commits_marks_executed_syncs_memory_and_emits_card():
    db = AsyncMock()
    output = {"success": True, "event_id": "event-1", "card": {"type": "event_created"}}
    execute = AsyncMock(return_value=output)
    sync_memory = Mock()
    emitted_cards = []

    async def on_card(card):
        emitted_cards.append(card)

    context = ToolDispatchContext(
        db=db,
        user_id="user-1",
        result=SimpleNamespace(tools_executed=set(), cards=[], confirm_cards=[]),
        on_card=on_card,
        lang="zh",
        image_urls=["/photo.jpg"],
        location={"lat": 1},
    )
    invocation = ToolInvocation(
        id="call-1",
        name="create_calendar_event",
        arguments={"title": "洗澡"},
    )

    result = await handle_tool_execution(
        invocation,
        context,
        validate=lambda name, args: [],
        execute=execute,
        sync_memory=sync_memory,
    )

    assert result == output
    execute.assert_awaited_once_with(
        "create_calendar_event",
        {"title": "洗澡"},
        db,
        "user-1",
        lang="zh",
        location={"lat": 1},
        image_urls=["/photo.jpg"],
    )
    db.commit.assert_awaited_once()
    assert context.result.tools_executed == {"create_calendar_event"}
    sync_memory.assert_called_once_with(invocation, output)
    assert context.result.cards == [{"type": "event_created"}]
    assert emitted_cards == [{"type": "event_created"}]


@pytest.mark.asyncio
async def test_handler_exception_returns_truncated_error():
    async def execute(*args, **kwargs):
        raise RuntimeError("x" * 300)

    result = await handle_tool_execution(
        ToolInvocation(id="call-1", name="create_pet", arguments={}),
        ToolDispatchContext(),
        validate=lambda name, args: [],
        execute=execute,
    )

    assert result == {"error": "x" * 200}


@pytest.mark.asyncio
async def test_partial_confirm_stores_action_and_emits_confirm_card():
    db = AsyncMock()
    tool_result = {
        "success": True,
        "needs_confirm": True,
        "confirm_tool": "update_pet_profile",
        "confirm_arguments": {"pet_id": "pet-1"},
        "confirm_description": "确认修改",
    }
    store_action = AsyncMock(return_value="action-1")
    emitted_cards = []

    async def on_card(card):
        emitted_cards.append(card)

    context = ToolDispatchContext(
        db=db,
        user_id="user-1",
        session_id="session-1",
        result=SimpleNamespace(tools_executed=set(), cards=[], confirm_cards=[]),
        on_card=on_card,
    )

    result = await handle_tool_execution(
        ToolInvocation(id="call-1", name="update_pet_profile", arguments={}),
        context,
        validate=lambda name, args: [],
        execute=AsyncMock(return_value=tool_result),
        store_pending_action=store_action,
    )

    assert result == tool_result
    store_action.assert_awaited_once_with(
        db=db,
        user_id="user-1",
        session_id="session-1",
        tool_name="update_pet_profile",
        arguments={"pet_id": "pet-1"},
        description="确认修改",
    )
    assert context.result.confirm_cards == [
        {"type": "confirm_action", "action_id": "action-1", "message": "确认修改"}
    ]
    assert emitted_cards == context.result.confirm_cards
