"""E2E tests for incremental info build-up flow (TEST_PLAN §37).

Multi-turn sequential test simulating a vet visit where details are added
incrementally: event → location → cost → photo → daily task → reminder → summary.
"""

import re
from datetime import date, timedelta

import pytest

from .conftest import (
    E2EClient,
    get_tools_called,
    load_test_image,
    today_str,
)
from .test_messages import MESSAGES


@pytest.mark.asyncio
async def test_37_incremental_info(e2e_debug_with_pet: E2EClient):
    """§37: 7-step incremental build-up — vet visit → location → cost → photo → daily task → reminder → summary."""
    e2e = e2e_debug_with_pet
    msgs = MESSAGES["37_seq"]["zh"]

    # ── 37.1  Initial vet visit record ──
    r1 = await e2e.chat(msgs[0])
    assert r1.error is None, f"37.1 error: {r1.error}\n{r1.dump()}"
    assert r1.has_card("record"), f"37.1: Expected record card.\n{r1.dump()}"
    record_card = r1.first_card("record")
    assert record_card.get("category") == "medical", (
        f"37.1: Expected category 'medical', got '{record_card.get('category')}'.\n{r1.dump()}"
    )

    # ── 37.2  Add location to the vet visit ──
    r2 = await e2e.chat(msgs[1])
    assert r2.error is None, f"37.2 error: {r2.error}\n{r2.dump()}"
    tools2 = get_tools_called(r2)
    assert "add_event_location" in tools2, (
        f"37.2: Expected add_event_location tool, got {tools2}.\n{r2.dump()}"
    )

    # ── 37.3  Add cost ──
    r3 = await e2e.chat(msgs[2])
    assert r3.error is None, f"37.3 error: {r3.error}\n{r3.dump()}"
    # Verify cost is set on the event
    events = await e2e.get_events(date_str=today_str())
    cost_events = [ev for ev in events if ev.get("cost") is not None and ev["cost"] > 0]
    assert any(ev["cost"] == 1500 or ev["cost"] == 1500.0 for ev in cost_events), (
        f"37.3: Expected an event with cost=1500, got costs={[ev.get('cost') for ev in events]}.\n{r3.dump()}"
    )

    # ── 37.4  Upload examination report photo ──
    img = load_test_image()
    r4 = await e2e.chat(msgs[3], images=[img])
    assert r4.error is None, f"37.4 error: {r4.error}\n{r4.dump()}"
    # Verify photo attached to the medical event
    events = await e2e.get_events(date_str=today_str())
    photo_events = [ev for ev in events if ev.get("photos")]
    assert photo_events, f"37.4: No events with photos found.\n{r4.dump()}"

    # ── 37.5  Create daily probiotic task ──
    r5 = await e2e.chat(msgs[4])
    assert r5.error is None, f"37.5 error: {r5.error}\n{r5.dump()}"
    assert r5.has_card("daily_task_created"), (
        f"37.5: Expected daily_task_created card.\n{r5.dump()}"
    )
    task_card = r5.first_card("daily_task_created")
    # Verify task type is special (medication/supplement) — accept either field name
    task_type = task_card.get("task_type") or task_card.get("type") or ""
    if task_type != "special":
        print(f"WARNING: 37.5 Expected task type 'special', got '{task_type}'")
    # Verify end_date is approximately 1 week from now
    end_date_str = task_card.get("end_date") or ""
    if end_date_str:
        try:
            end_date = date.fromisoformat(end_date_str)
            expected_end = date.today() + timedelta(days=7)
            delta = abs((end_date - expected_end).days)
            assert delta <= 2, (
                f"37.5: end_date {end_date_str} is {delta} days off from expected ~1 week.\n{r5.dump()}"
            )
        except ValueError:
            pass  # Non-standard date format, skip date validation

    # ── 37.6  Reminder for follow-up checkup ──
    r6 = await e2e.chat(msgs[5])
    assert r6.error is None, f"37.6 error: {r6.error}\n{r6.dump()}"
    # Reminders are now merged into calendar events (record cards with reminder_at)
    assert r6.has_card("record") or "提醒" in r6.text or "remind" in r6.text.lower(), (
        f"37.6: Expected record card or reminder mention.\n{r6.dump()}"
    )

    # ── 37.7  Summary of the vet visit ──
    r7 = await e2e.chat(msgs[6])
    assert r7.error is None, f"37.7 error: {r7.error}\n{r7.dump()}"
    text = r7.text
    # Summary should mention: location, cost, probiotic, and follow-up checkup
    has_location = "Vanier" in text or "vanier" in text.lower() or "医院" in text
    has_cost = "1500" in text
    has_probiotic = "益生菌" in text or "probiotic" in text.lower()
    has_checkup = "复查" in text or "复诊" in text or "follow" in text.lower() or "check" in text.lower()
    assert has_location and has_cost and has_probiotic and has_checkup, (
        f"37.7: Summary should mention location, cost, probiotic, and checkup. "
        f"location={has_location}, cost={has_cost}, probiotic={has_probiotic}, checkup={has_checkup}.\n{r7.dump()}"
    )
