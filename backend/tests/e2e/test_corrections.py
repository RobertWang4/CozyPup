"""E2E tests for record corrections (TEST_PLAN §24.1-24.3).

Verifies that the agent can update existing calendar events when the user
corrects a date, category, or title — using update_calendar_event rather
than creating a new event.
"""

import pytest

from .conftest import E2EClient, get_tools_called, today_str
from .test_messages import MESSAGES


# ═══════════════════════════════════════════════════════════════════════════
# 24.1 — Create vaccine event, then correct the date to March 25th
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_24_1_correct_date(e2e_debug_with_pet: E2EClient):
    """24.1 Create '小维今天打了疫苗', then '日期不对，应该是3月25号' -> update_calendar_event, event on 2026-03-25."""
    e2e = e2e_debug_with_pet

    # Setup: create a vaccine event
    setup = await e2e.chat("小维今天打了疫苗", language="zh")
    assert setup.error is None, f"Setup failed: {setup.error}"
    assert setup.has_card("record"), (
        f"Setup: expected a record card.\n{setup.dump()}"
    )

    # Correct the date
    result = await e2e.chat(MESSAGES["24.1"]["zh"], language="zh")
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"

    tools = get_tools_called(result)
    assert "update_calendar_event" in tools, (
        f"Expected update_calendar_event in tools_called (should update, not create new). "
        f"Got: {tools}\n{result.dump()}"
    )

    # Verify via API that an event exists on March 25th
    events = await e2e.get_events(date_str="2026-03-25")
    assert len(events) > 0, (
        f"Expected event on 2026-03-25 after date correction, found none.\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 24.2 — Create diet event, then correct category to medical
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_24_2_correct_category(e2e_debug_with_pet: E2EClient):
    """24.2 Create '小维今天吃了狗粮', then '分类应该是 medical 不是 diet' -> category updated."""
    e2e = e2e_debug_with_pet

    # Setup: create a diet event
    setup = await e2e.chat("小维今天吃了狗粮", language="zh")
    assert setup.error is None, f"Setup failed: {setup.error}"
    assert setup.has_card("record"), (
        f"Setup: expected a record card.\n{setup.dump()}"
    )

    # Correct the category
    result = await e2e.chat(MESSAGES["24.2"]["zh"], language="zh")
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"

    tools = get_tools_called(result)
    assert "update_calendar_event" in tools, (
        f"Expected update_calendar_event in tools_called. Got: {tools}\n{result.dump()}"
    )

    # Verify via API that today's event has category=medical
    events = await e2e.get_events(date_str=today_str())
    medical_events = [e for e in events if e.get("category") == "medical"]
    assert len(medical_events) > 0, (
        f"Expected at least one event with category=medical on {today_str()} after correction. "
        f"Events: {events}\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 24.3 — Create walk event, then correct title to "公园散步"
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_24_3_correct_title(e2e_debug_with_pet: E2EClient):
    """24.3 Create '小维今天散步了', then '改成公园散步' -> title updated."""
    e2e = e2e_debug_with_pet

    # Setup: create a walk event
    setup = await e2e.chat("小维今天散步了", language="zh")
    assert setup.error is None, f"Setup failed: {setup.error}"
    assert setup.has_card("record"), (
        f"Setup: expected a record card.\n{setup.dump()}"
    )

    # Correct the title
    result = await e2e.chat(MESSAGES["24.3"]["zh"], language="zh")
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"

    tools = get_tools_called(result)
    assert "update_calendar_event" in tools, (
        f"Expected update_calendar_event in tools_called. Got: {tools}\n{result.dump()}"
    )

    # Verify via API that today's event title contains "公园"
    events = await e2e.get_events(date_str=today_str())
    park_events = [
        e for e in events
        if "公园" in (e.get("title", "") or "")
    ]
    assert len(park_events) > 0, (
        f"Expected at least one event with '公园' in title on {today_str()} after correction. "
        f"Events: {[e.get('title') for e in events]}\n{result.dump()}"
    )
