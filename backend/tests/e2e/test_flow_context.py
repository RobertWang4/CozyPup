"""E2E tests for context reference & disambiguation (TEST_PLAN §27).

Multi-turn sequential test verifying that pronouns like "那个" and "刚才"
resolve correctly to prior records/reminders in conversation context.
"""

import pytest

from .conftest import (
    E2EClient,
    get_tools_called,
    today_str,
)
from .test_messages import MESSAGES


@pytest.mark.asyncio
async def test_27_context_reference(e2e_debug_with_pet: E2EClient):
    """§27: 6-step context reference — vaccine → cost update → reminder → rename → delete reminder → new record."""
    e2e = e2e_debug_with_pet
    msgs = MESSAGES["27_seq"]["zh"]

    # ── 27.1  Record vaccination ──
    r1 = await e2e.chat(msgs[0])
    assert r1.error is None, f"27.1 error: {r1.error}\n{r1.dump()}"
    assert r1.has_card("record"), f"27.1: Expected record card.\n{r1.dump()}"

    # Snapshot event count after first record
    events_after_1 = await e2e.get_events(date_str=today_str())
    count_after_1 = len(events_after_1)
    assert count_after_1 >= 1, f"27.1: Expected at least 1 event, got {count_after_1}.\n{r1.dump()}"

    # ── 27.2  Add cost to previous record (context: "花了200") ──
    r2 = await e2e.chat(msgs[1])
    assert r2.error is None, f"27.2 error: {r2.error}\n{r2.dump()}"
    tools2 = get_tools_called(r2)
    assert "update_calendar_event" in tools2, (
        f"27.2: Expected update_calendar_event (not new event), got {tools2}.\n{r2.dump()}"
    )

    # Verify cost was set and no new event was created
    events_after_2 = await e2e.get_events(date_str=today_str())
    assert len(events_after_2) == count_after_1, (
        f"27.2: Event count should stay at {count_after_1}, got {len(events_after_2)}. "
        f"Cost update should not create a new event.\n{r2.dump()}"
    )
    cost_events = [ev for ev in events_after_2 if ev.get("cost") is not None and ev["cost"] > 0]
    assert any(ev["cost"] == 200 or ev["cost"] == 200.0 for ev in cost_events), (
        f"27.2: Expected an event with cost=200, got costs={[ev.get('cost') for ev in events_after_2]}.\n{r2.dump()}"
    )

    # ── 27.3  Set reminder for next vaccination ──
    r3 = await e2e.chat(msgs[2])
    assert r3.error is None, f"27.3 error: {r3.error}\n{r3.dump()}"
    assert r3.has_card("reminder"), f"27.3: Expected reminder card.\n{r3.dump()}"

    # ── 27.4  Rename the vaccination record (context: "那条记录") ──
    r4 = await e2e.chat(msgs[3])
    assert r4.error is None, f"27.4 error: {r4.error}\n{r4.dump()}"
    tools4 = get_tools_called(r4)
    assert "update_calendar_event" in tools4, (
        f"27.4: Expected update_calendar_event for title rename, got {tools4}.\n{r4.dump()}"
    )

    # Verify title was updated
    events_after_4 = await e2e.get_events(date_str=today_str())
    vaccine_events = [ev for ev in events_after_4 if "疫苗" in (ev.get("title") or "")]
    assert vaccine_events, (
        f"27.4: Expected an event with '疫苗' in title after rename. "
        f"Titles: {[ev.get('title') for ev in events_after_4]}.\n{r4.dump()}"
    )

    # ── 27.5  Delete the reminder (context: "刚才那个提醒") ──
    r5 = await e2e.chat(msgs[4])
    assert r5.error is None, f"27.5 error: {r5.error}\n{r5.dump()}"
    assert r5.has_card("confirm_action"), (
        f"27.5: Expected confirm_action card for destructive delete.\n{r5.dump()}"
    )

    # ── 27.6  Record a new event (bath) — must be a NEW event, not an update ──
    r6 = await e2e.chat(msgs[5])
    assert r6.error is None, f"27.6 error: {r6.error}\n{r6.dump()}"
    assert r6.has_card("record"), f"27.6: Expected record card for new bath event.\n{r6.dump()}"

    # Verify a new event was created (count increased)
    events_after_6 = await e2e.get_events(date_str=today_str())
    assert len(events_after_6) > count_after_1, (
        f"27.6: Expected more events after adding bath. "
        f"Before={count_after_1}, after={len(events_after_6)}.\n{r6.dump()}"
    )
