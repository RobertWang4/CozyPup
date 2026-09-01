from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.tool_confirmation import handle_tool_confirmation
from app.agents.tool_context import ToolDispatchContext
from app.agents.tool_invocation import ToolInvocation


@pytest.mark.asyncio
async def test_create_pet_confirmation_stores_action_and_emits_card():
    result = SimpleNamespace(confirm_cards=[])
    emitted_cards = []

    async def on_card(card):
        emitted_cards.append(card)

    context = ToolDispatchContext(
        db=AsyncMock(),
        user_id="user-1",
        session_id="session-1",
        result=result,
        on_card=on_card,
        lang="zh",
        messages=[{"role": "user", "content": "我有一只公的可卡布叫维尼"}],
    )
    invocation = ToolInvocation(
        id="call-1",
        name="create_pet",
        arguments={
            "name": "维尼",
            "species": "dog",
            "gender": "male",
            "breed": "可卡布",
        },
    )

    with patch("app.agents.tool_confirmation.store_action", new_callable=AsyncMock, return_value="action-123") as store:
        output = await handle_tool_confirmation(invocation, context)

    assert output["status"] == "waiting_confirm"
    assert output["executed"] is False
    assert output["db_changed"] is False
    assert output["description"]
    store.assert_awaited_once_with(
        db=context.db,
        user_id="user-1",
        session_id="session-1",
        tool_name="create_pet",
        arguments=invocation.arguments,
        description=output["description"],
    )
    assert emitted_cards == result.confirm_cards
    assert result.confirm_cards[0]["action_id"] == "action-123"
    assert result.confirm_cards[0]["title"] == "新增宠物确认"
    assert result.confirm_cards[0]["fields"] == [
        {"label": "名字", "value": "维尼"},
        {"label": "性别", "value": "公"},
        {"label": "品种", "value": "可卡布"},
    ]


@pytest.mark.asyncio
async def test_calendar_event_confirmation_persists_image_urls():
    result = SimpleNamespace(confirm_cards=[])
    context = ToolDispatchContext(
        db=AsyncMock(),
        user_id="user-1",
        session_id="session-1",
        result=result,
        lang="zh",
        image_urls=["/api/v1/calendar/photos/photo.jpg"],
        messages=[{"role": "user", "content": "维尼看起来不错"}],
    )
    invocation = ToolInvocation(
        id="call-1",
        name="create_calendar_event",
        arguments={
            "pet_id": "pet-vinnie",
            "event_date": "2026-06-13",
            "title": "洗澡",
            "category": "daily",
        },
    )

    with patch("app.agents.tool_confirmation.store_action", new_callable=AsyncMock, return_value="action-123") as store:
        output = await handle_tool_confirmation(invocation, context)

    assert output["status"] == "waiting_confirm"
    stored_args = store.await_args.kwargs["arguments"]
    assert stored_args["_image_urls"] == ["/api/v1/calendar/photos/photo.jpg"]
    assert "_image_urls" not in invocation.arguments


@pytest.mark.asyncio
async def test_explicit_action_verb_skips_confirmation():
    context = ToolDispatchContext(
        session_id="session-1",
        messages=[{"role": "user", "content": "新增宠物维尼"}],
    )

    output = await handle_tool_confirmation(
        ToolInvocation(id="call-1", name="create_pet", arguments={"name": "维尼"}),
        context,
    )

    assert output is None
