"""E2E tests for mixed intent switching (TEST_PLAN §30).

Multi-turn sequential test verifying the LLM selects the correct tool
when the user rapidly switches between recording, health Q&A, map search,
reminders, daily tasks, and emergency — without cross-contamination.
"""

import pytest

from .conftest import (
    E2EClient,
    get_tools_called,
)
from .test_messages import MESSAGES


@pytest.mark.asyncio
async def test_30_mixed_intent_switching(e2e_debug_with_pet: E2EClient):
    """§30: 7-step mixed intent — record → health Q&A → map → reminder → daily task → emergency → all clear."""
    e2e = e2e_debug_with_pet
    msgs = MESSAGES["30_seq"]["zh"]

    # ── 30.1  Record feeding ──
    r1 = await e2e.chat(msgs[0])
    assert r1.error is None, f"30.1 error: {r1.error}\n{r1.dump()}"
    assert r1.has_card("record"), f"30.1: Expected record card.\n{r1.dump()}"

    # ── 30.2  Health Q&A: diarrhea advice (should use search_knowledge, NOT create event) ──
    r2 = await e2e.chat(msgs[1])
    assert r2.error is None, f"30.2 error: {r2.error}\n{r2.dump()}"
    tools2 = get_tools_called(r2)
    assert "search_knowledge" in tools2, (
        f"30.2: Expected search_knowledge for health question, got {tools2}.\n{r2.dump()}"
    )
    assert "create_calendar_event" not in tools2, (
        f"30.2: Should NOT create event for health question, but got {tools2}.\n{r2.dump()}"
    )

    # ── 30.3  Nearby pet hospital (should use search_places, NOT search_knowledge) ──
    r3 = await e2e.chat(
        msgs[2],
        location={"lat": 45.4215, "lng": -75.6972},
    )
    assert r3.error is None, f"30.3 error: {r3.error}\n{r3.dump()}"
    assert r3.has_card("place_card"), (
        f"30.3: Expected place_card for nearby search.\n{r3.dump()}"
    )
    tools3 = get_tools_called(r3)
    assert "search_knowledge" not in tools3, (
        f"30.3: Should NOT use search_knowledge for place search, but got {tools3}.\n{r3.dump()}"
    )

    # ── 30.4  Reminder to visit hospital tomorrow (should be reminder, NOT place search) ──
    r4 = await e2e.chat(msgs[3])
    assert r4.error is None, f"30.4 error: {r4.error}\n{r4.dump()}"
    # Reminders are now merged into calendar events (record cards with reminder_at)
    assert r4.has_card("record") or "提醒" in r4.text or "remind" in r4.text.lower(), (
        f"30.4: Expected record card or reminder mention.\n{r4.dump()}"
    )
    tools4 = get_tools_called(r4)
    assert "search_places" not in tools4, (
        f"30.4: Should NOT search places for reminder, but got {tools4}.\n{r4.dump()}"
    )

    # ── 30.5  Daily task: give probiotics every day (should be daily_task, NOT one-off reminder) ──
    r5 = await e2e.chat(msgs[4])
    assert r5.error is None, f"30.5 error: {r5.error}\n{r5.dump()}"
    assert r5.has_card("daily_task_created"), (
        f"30.5: Expected daily_task_created card.\n{r5.dump()}"
    )
    tools5 = get_tools_called(r5)
    assert "create_reminder" not in tools5, (
        f"30.5: Should NOT use create_reminder for daily task, but got {tools5}.\n{r5.dump()}"
    )

    # ── 30.6  Emergency: seizures ──
    r6 = await e2e.chat(msgs[5])
    assert r6.error is None, f"30.6 error: {r6.error}\n{r6.dump()}"
    assert r6.emergency is not None, (
        f"30.6: Expected emergency response for seizure report.\n{r6.dump()}"
    )

    # ── 30.7  All clear: "没事了，虚惊一场" — no emergency, no tools ──
    r7 = await e2e.chat(msgs[6])
    assert r7.error is None, f"30.7 error: {r7.error}\n{r7.dump()}"
    assert r7.emergency is None, (
        f"30.7: Should NOT trigger emergency for 'false alarm'.\n{r7.dump()}"
    )
    tools7 = get_tools_called(r7)
    assert len(tools7) == 0, (
        f"30.7: Expected no tool calls for casual 'false alarm', got {tools7}.\n{r7.dump()}"
    )
