from datetime import date
from types import SimpleNamespace

from app.agents.tool_context import ToolDispatchContext
from app.agents.tool_guards import apply_tool_guards
from app.agents.tool_invocation import ToolInvocation


def test_blocks_calendar_event_for_unmentioned_pet():
    pets = [
        SimpleNamespace(id="pet-vinnie", name="维尼"),
        SimpleNamespace(id="pet-huahua", name="花花"),
    ]
    context = ToolDispatchContext(
        pets=pets,
        messages=[{"role": "user", "content": "维尼今天吃了狗粮"}],
    )

    result = apply_tool_guards(
        ToolInvocation(
            id="call-1",
            name="create_calendar_event",
            arguments={"pet_id": "pet-huahua"},
        ),
        context,
    )

    assert result == {
        "success": False,
        "error": "用户只提到了特定的宠物，没有提到花花。请只为用户提到的宠物创建事件。",
    }


def test_blocks_duplicate_pet_creation():
    pets = [SimpleNamespace(id="pet-vinnie", name="维尼")]
    context = ToolDispatchContext(pets=pets)

    result = apply_tool_guards(
        ToolInvocation(
            id="call-1",
            name="create_pet",
            arguments={"name": " 维尼 "},
        ),
        context,
    )

    assert result == {
        "success": False,
        "error": (
            "宠物「维尼」已经存在 (id=pet-vinnie)。"
            "不要重复创建 — 如需补充信息，请改用 update_pet_profile 并传 pet_id。"
        ),
    }


def test_backfills_calendar_event_cost_from_user_text():
    invocation = ToolInvocation(
        id="call-1",
        name="create_calendar_event",
        arguments={"cost": None},
    )
    context = ToolDispatchContext(
        messages=[{"role": "user", "content": "维尼今天洗澡花了300块"}],
    )

    result = apply_tool_guards(invocation, context)

    assert result is None
    assert invocation.arguments["cost"] == 300.0


def test_backfills_daily_task_end_date_from_next_days():
    invocation = ToolInvocation(
        id="call-1",
        name="create_daily_task",
        arguments={},
    )
    context = ToolDispatchContext(
        messages=[{"role": "user", "content": "接下来7天每天提醒我喂药"}],
    )

    result = apply_tool_guards(invocation, context, today=date(2026, 6, 13))

    assert result is None
    assert invocation.arguments["end_date"] == "2026-06-20"


def test_non_guarded_tool_passes_through():
    result = apply_tool_guards(
        ToolInvocation(id="call-1", name="query_calendar_events", arguments={}),
        ToolDispatchContext(),
    )

    assert result is None
