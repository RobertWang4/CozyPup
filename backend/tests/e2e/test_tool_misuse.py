"""E2E tests for tool misuse defense (TEST_PLAN section 38).

Verifies the LLM does NOT call the wrong tool for ambiguous or
off-topic inputs. Each test sends a message and checks that
specific tools are absent from the trace.
"""

import pytest

from .conftest import E2EClient, get_tools_called, today_str
from .test_messages import MESSAGES


# ---------------------------------------------------------------------------
# 38.1  Pure chat — no tools at all
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_38_1_weather_chat_no_tools(e2e_debug: E2EClient, lang: str):
    """38.1 'The weather is nice' should be pure chat — no tools called."""
    result = await e2e_debug.chat(MESSAGES["38.1"][lang])
    assert result.error is None, f"38.1 error: {result.error}\n{result.dump()}"
    assert result.text.strip(), f"38.1: Expected non-empty reply.\n{result.dump()}"
    tools = get_tools_called(result)
    assert tools == [], (
        f"38.1: Expected no tools, got {tools}.\n{result.dump()}"
    )


# ---------------------------------------------------------------------------
# 38.2  Opinion question — no create_pet, no search_knowledge
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_38_2_opinion_no_create_pet(e2e_debug: E2EClient, lang: str):
    """38.2 Breed opinion question should NOT trigger create_pet or search_knowledge."""
    result = await e2e_debug.chat(MESSAGES["38.2"][lang])
    assert result.error is None, f"38.2 error: {result.error}\n{result.dump()}"
    assert result.text.strip(), f"38.2: Expected non-empty reply.\n{result.dump()}"
    tools = get_tools_called(result)
    assert "create_pet" not in tools, (
        f"38.2: create_pet should NOT be called, got {tools}.\n{result.dump()}"
    )
    assert "search_knowledge" not in tools, (
        f"38.2: search_knowledge should NOT be called, got {tools}.\n{result.dump()}"
    )


# ---------------------------------------------------------------------------
# 38.3  Compliment about pet — no create_calendar_event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_38_3_compliment_no_event(e2e_debug_with_pet: E2EClient, lang: str):
    """38.3 'Weiwei is so cute' should NOT create a calendar event."""
    result = await e2e_debug_with_pet.chat(MESSAGES["38.3"][lang])
    assert result.error is None, f"38.3 error: {result.error}\n{result.dump()}"
    assert result.text.strip(), f"38.3: Expected non-empty reply.\n{result.dump()}"
    tools = get_tools_called(result)
    assert "create_calendar_event" not in tools, (
        f"38.3: create_calendar_event should NOT be called, got {tools}.\n{result.dump()}"
    )


# ---------------------------------------------------------------------------
# 38.4  'Look up my pets' — list_pets, NOT query_calendar_events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
@pytest.mark.xfail(reason="LLM sometimes skips list_pets tool call")
async def test_38_4_lookup_pets_correct_tool(e2e_debug: E2EClient, lang: str):
    """38.4 'Look up my pets' should call list_pets, NOT query_calendar_events."""
    result = await e2e_debug.chat(MESSAGES["38.4"][lang])
    assert result.error is None, f"38.4 error: {result.error}\n{result.dump()}"
    tools = get_tools_called(result)
    assert "list_pets" in tools, (
        f"38.4: Expected list_pets in tools, got {tools}.\n{result.dump()}"
    )
    assert "query_calendar_events" not in tools, (
        f"38.4: query_calendar_events should NOT be called, got {tools}.\n{result.dump()}"
    )


# ---------------------------------------------------------------------------
# 38.5  'My tasks' — list_daily_tasks, NOT manage_daily_task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_38_5_my_tasks_correct_tool(e2e_debug: E2EClient, lang: str):
    """38.5 'My tasks' should call list_daily_tasks, NOT manage_daily_task."""
    result = await e2e_debug.chat(MESSAGES["38.5"][lang])
    assert result.error is None, f"38.5 error: {result.error}\n{result.dump()}"
    tools = get_tools_called(result)
    assert "list_daily_tasks" in tools, (
        f"38.5: Expected list_daily_tasks in tools, got {tools}.\n{result.dump()}"
    )
    assert "manage_daily_task" not in tools, (
        f"38.5: manage_daily_task should NOT be called, got {tools}.\n{result.dump()}"
    )


# ---------------------------------------------------------------------------
# 38.6  'This record is wrong' — should ask for clarification, not delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_38_6_vague_correction_asks_clarification(
    e2e_debug_with_pet: E2EClient, lang: str
):
    """38.6 'This record is wrong' with no specifics — should ask what's wrong, not delete."""
    e2e = e2e_debug_with_pet
    # First create a record so there's something to reference
    await e2e.chat("小维今天吃了狗粮" if lang == "zh" else "Weiwei ate dog food today")

    result = await e2e.chat(MESSAGES["38.6"][lang])
    assert result.error is None, f"38.6 error: {result.error}\n{result.dump()}"
    # LLM may respond with text or a card; main check is no deletion
    tools = get_tools_called(result)
    assert "delete_calendar_event" not in tools, (
        f"38.6: delete_calendar_event should NOT be called without specifics, got {tools}.\n{result.dump()}"
    )


# ---------------------------------------------------------------------------
# 38.7  Poisoning history query — NOT emergency, should query events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_38_7_poisoning_history_not_emergency(
    e2e_debug_with_pet: E2EClient, lang: str
):
    """38.7 'When was Weiwei's last poisoning?' — should query events, NOT trigger emergency."""
    result = await e2e_debug_with_pet.chat(MESSAGES["38.7"][lang])
    assert result.error is None, f"38.7 error: {result.error}\n{result.dump()}"
    assert result.emergency is None, (
        f"38.7: Should NOT trigger emergency for a history query.\n{result.dump()}"
    )
    tools = get_tools_called(result)
    assert "query_calendar_events" in tools, (
        f"38.7: Expected query_calendar_events, got {tools}.\n{result.dump()}"
    )


# ---------------------------------------------------------------------------
# 38.8  Duplicate pet name — should NOT create_pet again
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
@pytest.mark.xfail(reason="LLM sometimes creates duplicate pet anyway")
async def test_38_8_duplicate_pet_not_created(
    e2e_debug_with_pet: E2EClient, lang: str
):
    """38.8 'I got a new dog named Weiwei' when pet already exists — should NOT create duplicate."""
    result = await e2e_debug_with_pet.chat(MESSAGES["38.8"][lang])
    assert result.error is None, f"38.8 error: {result.error}\n{result.dump()}"
    tools = get_tools_called(result)
    assert "create_pet" not in tools, (
        f"38.8: create_pet should NOT be called for duplicate name, got {tools}.\n{result.dump()}"
    )
    # Verify still only one pet
    pets = await e2e_debug_with_pet.get_pets()
    weiwei_pets = [p for p in pets if "维" in p.get("name", "") or "weiwei" in p.get("name", "").lower()]
    assert len(weiwei_pets) == 1, (
        f"38.8: Expected 1 Weiwei pet, got {len(weiwei_pets)}.\n{result.dump()}"
    )
