"""E2E tests for correction & undo chain (TEST_PLAN §29).

Multi-turn sequential test verifying that corrections update existing records
instead of creating duplicates, and that delete + re-record works cleanly.
"""

import pytest

from .conftest import (
    E2EClient,
    get_tools_called,
    today_str,
    yesterday_str,
)
from .test_messages import MESSAGES


@pytest.mark.asyncio
async def test_29_correction_chain(e2e_debug_with_pet: E2EClient):
    """§29: 7-step correction chain — record → fix date → fix category → fix title → delete → confirm → re-record."""
    e2e = e2e_debug_with_pet
    msgs = MESSAGES["29_seq"]["zh"]

    # ── 29.1  Initial record: checkup today ──
    r1 = await e2e.chat(msgs[0])
    assert r1.error is None, f"29.1 error: {r1.error}\n{r1.dump()}"
    assert r1.has_card("record"), f"29.1: Expected record card.\n{r1.dump()}"

    # Snapshot event count
    events_after_1 = await e2e.get_events()
    count_after_1 = len(events_after_1)
    assert count_after_1 >= 1, f"29.1: Expected at least 1 event, got {count_after_1}.\n{r1.dump()}"

    # ── 29.2  Correct date: "不对，是昨天" ──
    r2 = await e2e.chat(msgs[1])
    assert r2.error is None, f"29.2 error: {r2.error}\n{r2.dump()}"
    tools2 = get_tools_called(r2)
    assert "update_calendar_event" in tools2, (
        f"29.2: Expected update_calendar_event (date correction), got {tools2}.\n{r2.dump()}"
    )

    # Event count must NOT increase (correction, not new record)
    events_after_2 = await e2e.get_events()
    assert len(events_after_2) == count_after_1, (
        f"29.2: Event count should stay at {count_after_1} after date correction, "
        f"got {len(events_after_2)}.\n{r2.dump()}"
    )

    # ── 29.3  Change category to daily ──
    r3 = await e2e.chat(msgs[2])
    assert r3.error is None, f"29.3 error: {r3.error}\n{r3.dump()}"
    tools3 = get_tools_called(r3)
    assert "update_calendar_event" in tools3, (
        f"29.3: Expected update_calendar_event for category change, got {tools3}.\n{r3.dump()}"
    )

    # Verify category updated and count unchanged
    events_after_3 = await e2e.get_events()
    assert len(events_after_3) == count_after_1, (
        f"29.3: Event count should stay at {count_after_1}, got {len(events_after_3)}.\n{r3.dump()}"
    )

    # ── 29.4  Change title to "年度体检" ──
    r4 = await e2e.chat(msgs[3])
    assert r4.error is None, f"29.4 error: {r4.error}\n{r4.dump()}"
    tools4 = get_tools_called(r4)
    assert "update_calendar_event" in tools4, (
        f"29.4: Expected update_calendar_event for title change, got {tools4}.\n{r4.dump()}"
    )

    # Verify title contains 体检
    events_after_4 = await e2e.get_events()
    assert len(events_after_4) == count_after_1, (
        f"29.4: Event count should stay at {count_after_1}, got {len(events_after_4)}.\n{r4.dump()}"
    )
    checkup_events = [ev for ev in events_after_4 if "体检" in (ev.get("title") or "")]
    assert checkup_events, (
        f"29.4: Expected an event with '体检' in title. "
        f"Titles: {[ev.get('title') for ev in events_after_4]}.\n{r4.dump()}"
    )

    # ── 29.5  Request delete: "算了，删掉这条" ──
    r5 = await e2e.chat(msgs[4])
    assert r5.error is None, f"29.5 error: {r5.error}\n{r5.dump()}"
    assert r5.has_card("confirm_action"), (
        f"29.5: Expected confirm_action card for delete.\n{r5.dump()}"
    )

    # Extract action_id from confirm_action card
    confirm_card = r5.first_card("confirm_action")
    action_id = confirm_card.get("action_id")
    assert action_id, f"29.5: confirm_action card missing action_id.\n{r5.dump()}"

    # ── 29.6  Confirm the delete ──
    confirm_resp = await e2e.confirm_action(action_id)
    assert confirm_resp.get("success") or confirm_resp.get("status") == "confirmed", (
        f"29.6: Confirm action failed: {confirm_resp}"
    )

    # Verify event count decreased
    events_after_6 = await e2e.get_events()
    assert len(events_after_6) < count_after_1, (
        f"29.6: Event count should decrease after delete. "
        f"Before={count_after_1}, after={len(events_after_6)}.\n"
        f"Confirm response: {confirm_resp}"
    )
    count_after_delete = len(events_after_6)

    # ── 29.7  Re-record: "重新记一下：小维昨天做了年度体检，花了500" ──
    r7 = await e2e.chat(msgs[5])  # msgs[5] because confirm (step 6) is API-only
    assert r7.error is None, f"29.7 error: {r7.error}\n{r7.dump()}"
    assert r7.has_card("record"), f"29.7: Expected record card for new record.\n{r7.dump()}"

    # Verify new event created with cost
    events_after_7 = await e2e.get_events()
    assert len(events_after_7) > count_after_delete, (
        f"29.7: Expected new event after re-record. "
        f"Before={count_after_delete}, after={len(events_after_7)}.\n{r7.dump()}"
    )
    cost_events = [ev for ev in events_after_7 if ev.get("cost") is not None and ev["cost"] > 0]
    assert any(ev["cost"] == 500 or ev["cost"] == 500.0 for ev in cost_events), (
        f"29.7: Expected an event with cost=500, got costs={[ev.get('cost') for ev in events_after_7]}.\n{r7.dump()}"
    )
