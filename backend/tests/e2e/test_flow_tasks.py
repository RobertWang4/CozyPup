"""E2E tests for task lifecycle multi-turn flow (TEST_PLAN §34).

9-step sequential test: create routine task → create twice-daily task →
create special task → list tasks → update task → cancel task (confirm) →
verify → delete all (confirm) → verify empty.
"""

import pytest

from .conftest import (
    E2EClient,
    get_tools_called,
)
from .test_messages import MESSAGES


@pytest.mark.asyncio
async def test_34_task_lifecycle(e2e_debug_with_pet: E2EClient):
    """§34: Task lifecycle — create × 3 → list → update → cancel → delete all."""
    e2e = e2e_debug_with_pet
    msgs = MESSAGES["34_seq"]["zh"]

    # ── 34.1  Create routine task: walk dog daily ──
    r1 = await e2e.chat(msgs[0])
    assert r1.error is None, f"34.1 error: {r1.error}\n{r1.dump()}"
    assert r1.has_card("task_created"), f"34.1: Expected task_created card.\n{r1.dump()}"
    card1 = r1.first_card("task_created")
    assert card1.get("task_type") == "routine", (
        f"34.1: Expected task_type 'routine', got '{card1.get('task_type')}'.\n{r1.dump()}"
    )

    # ── 34.2  Create task: medicine twice daily ──
    r2 = await e2e.chat(msgs[1])
    assert r2.error is None, f"34.2 error: {r2.error}\n{r2.dump()}"
    assert r2.has_card("task_created"), f"34.2: Expected task_created card.\n{r2.dump()}"
    card2 = r2.first_card("task_created")
    assert card2.get("daily_target") == 2, (
        f"34.2: Expected daily_target=2, got {card2.get('daily_target')}.\n{r2.dump()}"
    )

    # ── 34.3  Create special task: temperature this week ──
    r3 = await e2e.chat(msgs[2])
    assert r3.error is None, f"34.3 error: {r3.error}\n{r3.dump()}"
    assert r3.has_card("task_created"), f"34.3: Expected task_created card.\n{r3.dump()}"
    card3 = r3.first_card("task_created")
    assert card3.get("task_type") == "special", (
        f"34.3: Expected task_type 'special', got '{card3.get('task_type')}'.\n{r3.dump()}"
    )
    assert card3.get("end_date"), (
        f"34.3: Special task should have end_date.\n{r3.dump()}"
    )

    # ── 34.4  List all tasks ──
    r4 = await e2e.chat(msgs[3])
    assert r4.error is None, f"34.4 error: {r4.error}\n{r4.dump()}"
    tools4 = get_tools_called(r4)
    assert "list_daily_tasks" in tools4, (
        f"34.4: Expected list_daily_tasks tool call, got {tools4}.\n{r4.dump()}"
    )
    text4 = r4.text
    assert ("遛狗" in text4 or "walk" in text4.lower()), (
        f"34.4: Should mention walking task.\n{r4.dump()}"
    )
    assert ("药" in text4 or "medicine" in text4.lower()), (
        f"34.4: Should mention medicine task.\n{r4.dump()}"
    )
    assert ("体温" in text4 or "temperature" in text4.lower()), (
        f"34.4: Should mention temperature task.\n{r4.dump()}"
    )

    # ── 34.5  Update medicine to 3× daily ──
    r5 = await e2e.chat(msgs[4])
    assert r5.error is None, f"34.5 error: {r5.error}\n{r5.dump()}"
    # Verify via API that target was updated
    tasks = await e2e.get_tasks_today()
    med_tasks = [
        t for t in tasks
        if "药" in t.get("name", "") or "medicine" in t.get("name", "").lower()
    ]
    if med_tasks:
        assert med_tasks[0].get("daily_target") == 3, (
            f"34.5: Expected daily_target=3 for medicine task, got {med_tasks[0].get('daily_target')}.\n{r5.dump()}"
        )

    # ── 34.6  Cancel temperature task → confirm_action ──
    r6 = await e2e.chat(msgs[5])
    assert r6.error is None, f"34.6 error: {r6.error}\n{r6.dump()}"
    assert r6.has_card("confirm_action"), (
        f"34.6: Expected confirm_action card.\n{r6.dump()}"
    )
    confirm_card_6 = r6.first_card("confirm_action")
    action_id_6 = confirm_card_6.get("action_id")
    assert action_id_6, f"34.6: confirm_action card should have action_id.\n{r6.dump()}"

    # ── 34.7  Confirm deletion → tasks decrease ──
    confirm_result_7 = await e2e.confirm_action(action_id_6)
    assert confirm_result_7, "34.7: confirm_action should return a response."
    tasks_after = await e2e.get_tasks_today()
    assert len(tasks_after) == 2, (
        f"34.7: Expected 2 remaining tasks, got {len(tasks_after)}.\n"
        f"Tasks: {[t.get('name') for t in tasks_after]}"
    )

    # ── 34.8  Delete all tasks → confirm_action ──
    r8 = await e2e.chat(msgs[6])
    assert r8.error is None, f"34.8 error: {r8.error}\n{r8.dump()}"
    assert r8.has_card("confirm_action"), (
        f"34.8: Expected confirm_action card.\n{r8.dump()}"
    )
    confirm_card_8 = r8.first_card("confirm_action")
    action_id_8 = confirm_card_8.get("action_id")
    assert action_id_8, f"34.8: confirm_action card should have action_id.\n{r8.dump()}"

    # ── 34.9  Confirm delete all → tasks = 0 ──
    confirm_result_9 = await e2e.confirm_action(action_id_8)
    assert confirm_result_9, "34.9: confirm_action should return a response."
    tasks_final = await e2e.get_tasks_today()
    assert len(tasks_final) == 0, (
        f"34.9: Expected 0 tasks after delete all, got {len(tasks_final)}.\n"
        f"Tasks: {[t.get('name') for t in tasks_final]}"
    )
