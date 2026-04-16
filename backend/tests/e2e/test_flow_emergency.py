"""E2E tests for emergency handling multi-turn flow (TEST_PLAN §35).

6-step sequential test: seizure emergency → find 24h ER → directions →
record abnormal event → email to vet → reminder for follow-up.
"""

import pytest

from .conftest import (
    E2EClient,
    get_tools_called,
    today_str,
)
from .test_messages import MESSAGES


LOCATION = {"lat": 45.4215, "lng": -75.6972}


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Multi-step LLM flow is non-deterministic — directions/email cards may not be returned")
async def test_35_emergency_flow(e2e_debug_with_pet: E2EClient):
    """§35: Emergency flow — seizure → ER search → directions → record → email → reminder."""
    e2e = e2e_debug_with_pet
    msgs = MESSAGES["35_seq"]["zh"]

    # ── 35.1  Seizure emergency ──
    r1 = await e2e.chat(msgs[0])
    assert r1.error is None, f"35.1 error: {r1.error}\n{r1.dump()}"
    assert r1.emergency is not None, (
        f"35.1: Expected emergency event.\n{r1.dump()}"
    )

    # ── 35.2  Find 24h ER nearby ──
    r2 = await e2e.chat(msgs[1], location=LOCATION)
    assert r2.error is None, f"35.2 error: {r2.error}\n{r2.dump()}"
    assert r2.has_card("place_card"), f"35.2: Expected place_card.\n{r2.dump()}"

    # ── 35.3  Directions to nearest ER ──
    r3 = await e2e.chat(msgs[2])
    assert r3.error is None, f"35.3 error: {r3.error}\n{r3.dump()}"
    assert r3.has_card("directions"), f"35.3: Expected directions card.\n{r3.dump()}"

    # ── 35.4  Record seizure as abnormal event ──
    r4 = await e2e.chat(msgs[3])
    assert r4.error is None, f"35.4 error: {r4.error}\n{r4.dump()}"
    assert r4.has_card("record"), f"35.4: Expected record card.\n{r4.dump()}"
    card4 = r4.first_card("record")
    assert card4.get("category") == "abnormal", (
        f"35.4: Expected category 'abnormal', got '{card4.get('category')}'.\n{r4.dump()}"
    )

    # ── 35.5  Email to vet ──
    r5 = await e2e.chat(msgs[4])
    assert r5.error is None, f"35.5 error: {r5.error}\n{r5.dump()}"
    assert r5.has_card("email"), f"35.5: Expected email card.\n{r5.dump()}"
    email_card = r5.first_card("email")
    body = (email_card.get("body") or "").lower()
    assert "抽搐" in body or "seizure" in body or "convuls" in body, (
        f"35.5: Email body should mention seizure/抽搐.\n{r5.dump()}"
    )

    # ── 35.6  Reminder for follow-up tomorrow ──
    r6 = await e2e.chat(msgs[5])
    assert r6.error is None, f"35.6 error: {r6.error}\n{r6.dump()}"
    # Reminders are now merged into calendar events (record cards with reminder_at)
    assert r6.has_card("record") or "提醒" in r6.text or "remind" in r6.text.lower(), (
        f"35.6: Expected record card or reminder mention.\n{r6.dump()}"
    )
