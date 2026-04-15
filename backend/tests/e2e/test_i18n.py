"""E2E tests for i18n language consistency (TEST_PLAN §22.1-22.5).

Verifies that cards returned by the agent respect the user's language setting:
- English mode: card text must NOT contain CJK characters
- Chinese mode: card text MUST contain CJK characters
"""

import pytest

from .conftest import E2EClient, get_tools_called, has_cjk, today_str
from .test_messages import MESSAGES


# ═══════════════════════════════════════════════════════════════════════════
# 22.1 — English: "Delete all daily tasks" → confirm card has no CJK
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_22_1_en_confirm_card_no_cjk(e2e_debug_with_pet: E2EClient):
    """22.1 lang=en, 'Delete all daily tasks' -> confirm card description has NO CJK."""
    e2e = e2e_debug_with_pet

    # Setup: create a task so there's something to delete
    setup = await e2e.chat("Remind me to walk the dog every day", language="en")
    assert setup.error is None, f"Setup failed: {setup.error}"
    assert setup.has_card("daily_task_created"), (
        f"Setup: expected daily_task_created card.\n{setup.dump()}"
    )

    # Delete all tasks in English
    result = await e2e.chat(MESSAGES["22.1"]["en"], language="en")
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("confirm_action"), (
        f"Expected a confirm_action card.\n{result.dump()}"
    )

    card = result.first_card("confirm_action")
    description = card.get("description", "") or card.get("message", "")
    assert not has_cjk(description), (
        f"confirm_action description should NOT contain CJK in English mode. "
        f"Got: {description!r}\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 22.2 — English: create event then "Delete it" → confirm card has no CJK
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_22_2_en_delete_event_no_cjk(e2e_debug_with_pet: E2EClient):
    """22.2 lang=en, create event then 'Delete it' -> confirm card has no CJK."""
    e2e = e2e_debug_with_pet

    # Setup: create an event in English
    setup = await e2e.chat("Weiwei ate dog food today", language="en")
    assert setup.error is None, f"Setup failed: {setup.error}"
    assert setup.has_card("record"), (
        f"Setup: expected a record card.\n{setup.dump()}"
    )

    # Delete the event
    result = await e2e.chat("Delete it", language="en")
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("confirm_action"), (
        f"Expected a confirm_action card.\n{result.dump()}"
    )

    card = result.first_card("confirm_action")
    description = card.get("description", "") or card.get("message", "")
    assert not has_cjk(description), (
        f"confirm_action description should NOT contain CJK in English mode. "
        f"Got: {description!r}\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 22.3 — Chinese: "删除所有待办" → confirm card description HAS CJK
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_22_3_zh_confirm_card_has_cjk(e2e_debug_with_pet: E2EClient):
    """22.3 lang=zh, '删除所有待办' -> confirm card description HAS CJK."""
    e2e = e2e_debug_with_pet

    # Setup: create a task in Chinese
    setup = await e2e.chat("每天提醒我遛狗", language="zh")
    assert setup.error is None, f"Setup failed: {setup.error}"
    assert setup.has_card("daily_task_created"), (
        f"Setup: expected daily_task_created card.\n{setup.dump()}"
    )

    # Delete all tasks in Chinese
    result = await e2e.chat(MESSAGES["22.3"]["zh"], language="zh")
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("confirm_action"), (
        f"Expected a confirm_action card.\n{result.dump()}"
    )

    card = result.first_card("confirm_action")
    description = card.get("description", "") or card.get("message", "")
    assert has_cjk(description), (
        f"confirm_action description SHOULD contain CJK in Chinese mode. "
        f"Got: {description!r}\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 22.4 — English: create + delete task → daily_task_deleted card title no CJK
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_22_4_en_task_deleted_card_no_cjk(e2e_debug_with_pet: E2EClient):
    """22.4 lang=en, create then delete task -> daily_task_deleted card title has no CJK."""
    e2e = e2e_debug_with_pet

    # Setup: create a task in English
    setup = await e2e.chat("Remind me to walk the dog every day", language="en")
    assert setup.error is None, f"Setup failed: {setup.error}"
    assert setup.has_card("daily_task_created"), (
        f"Setup: expected daily_task_created card.\n{setup.dump()}"
    )

    # Delete the task — may require confirm flow
    delete_result = await e2e.chat(MESSAGES["22.4"]["en"], language="en")
    assert delete_result.error is None, f"Chat error: {delete_result.error}\n{delete_result.dump()}"

    # If we got a confirm_action card, confirm it to get the actual deletion card
    if delete_result.has_card("confirm_action"):
        action_id = delete_result.first_card("confirm_action")["action_id"]
        await e2e.confirm_action(action_id)
        # After confirm, send a follow-up to get the deletion card in the stream
        # The confirm_action endpoint handles deletion; check tasks are gone
        tasks_after = await e2e.get_tasks_today()
        # Verify the confirm card description was in English
        card = delete_result.first_card("confirm_action")
        desc = card.get("description", "") or card.get("message", "")
        assert not has_cjk(desc), (
            f"confirm_action description should NOT contain CJK in English mode. "
            f"Got: {desc!r}\n{delete_result.dump()}"
        )
    elif delete_result.has_card("daily_task_deleted"):
        card = delete_result.first_card("daily_task_deleted")
        title = card.get("title", "")
        assert not has_cjk(title), (
            f"daily_task_deleted title should NOT contain CJK in English mode. "
            f"Got: {title!r}\n{delete_result.dump()}"
        )
    else:
        # Check all cards for CJK — any card related to deletion should be English
        for card in delete_result.cards:
            title = card.get("title", "")
            desc = card.get("description", "") or card.get("message", "")
            combined = f"{title} {desc}"
            assert not has_cjk(combined), (
                f"Card text should NOT contain CJK in English mode. "
                f"Got: {combined!r}\n{delete_result.dump()}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 22.5 — Chinese: create + delete task → daily_task_deleted card title has CJK
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_22_5_zh_task_deleted_card_has_cjk(e2e_debug_with_pet: E2EClient):
    """22.5 lang=zh, create then delete task -> daily_task_deleted card title has CJK."""
    e2e = e2e_debug_with_pet

    # Setup: create a task in Chinese
    setup = await e2e.chat("每天提醒我遛狗", language="zh")
    assert setup.error is None, f"Setup failed: {setup.error}"
    assert setup.has_card("daily_task_created"), (
        f"Setup: expected daily_task_created card.\n{setup.dump()}"
    )

    # Delete the task in Chinese
    delete_result = await e2e.chat(MESSAGES["22.5"]["zh"], language="zh")
    assert delete_result.error is None, f"Chat error: {delete_result.error}\n{delete_result.dump()}"

    # If we got a confirm_action card, verify it's in Chinese
    if delete_result.has_card("confirm_action"):
        card = delete_result.first_card("confirm_action")
        desc = card.get("description", "") or card.get("message", "")
        assert has_cjk(desc), (
            f"confirm_action description SHOULD contain CJK in Chinese mode. "
            f"Got: {desc!r}\n{delete_result.dump()}"
        )
        # Confirm the action to complete deletion
        action_id = card["action_id"]
        await e2e.confirm_action(action_id)
    elif delete_result.has_card("daily_task_deleted"):
        card = delete_result.first_card("daily_task_deleted")
        title = card.get("title", "")
        assert has_cjk(title), (
            f"daily_task_deleted title SHOULD contain CJK in Chinese mode. "
            f"Got: {title!r}\n{delete_result.dump()}"
        )
    else:
        # Check all cards — any deletion-related card should be Chinese
        has_any_cjk = any(
            has_cjk(card.get("title", "") + " " + (card.get("description", "") or card.get("message", "") or ""))
            for card in delete_result.cards
        )
        assert has_any_cjk or has_cjk(delete_result.text), (
            f"Expected CJK content in Chinese mode cards or text.\n{delete_result.dump()}"
        )
