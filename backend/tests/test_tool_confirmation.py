from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.tool_confirmation import build_confirm_card
from app.agents.tool_context import ToolDispatchContext
from app.agents.tool_invocation import ToolInvocation


@pytest.mark.asyncio
async def test_create_pet_confirmation_builds_card_with_thread_action_id():
    context = ToolDispatchContext(
        db=AsyncMock(),
        user_id="user-1",
        session_id="session-1",
        result=SimpleNamespace(confirm_cards=[]),
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

    card = await build_confirm_card(invocation, context, action_id="user-1:corr-1")

    assert card["type"] == "confirm_action"
    assert card["action_id"] == "user-1:corr-1"
    assert card["message"]
    assert card["title"] == "新增宠物确认"
    assert card["fields"] == [
        {"label": "名字", "value": "维尼"},
        {"label": "性别", "value": "公"},
        {"label": "品种", "value": "可卡布"},
    ]


@pytest.mark.asyncio
async def test_build_confirm_card_has_no_side_effects():
    """The confirm node re-runs from the top on resume — this must stay pure."""
    context = ToolDispatchContext(
        db=AsyncMock(),
        user_id="user-1",
        session_id="session-1",
        result=SimpleNamespace(confirm_cards=[]),
        on_card=AsyncMock(),
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

    first = await build_confirm_card(invocation, context, action_id="t1")
    second = await build_confirm_card(invocation, context, action_id="t1")

    assert first == second
    assert context.result.confirm_cards == []
    context.on_card.assert_not_awaited()
    assert "_image_urls" not in invocation.arguments


@pytest.mark.asyncio
async def test_explicit_action_verb_skips_confirmation():
    context = ToolDispatchContext(
        session_id="session-1",
        messages=[{"role": "user", "content": "新增宠物维尼"}],
    )

    card = await build_confirm_card(
        ToolInvocation(id="call-1", name="create_pet", arguments={"name": "维尼"}),
        context,
        action_id="t1",
    )

    assert card is None
