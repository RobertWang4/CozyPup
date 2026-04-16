"""E2E tests for dual pet daily flow (TEST_PLAN §33).

7-step sequential test: feed dog → feed cat → joint park visit →
dog vomits → query cat's diet → reminder for dog → reminder for cat.
"""

import pytest

from .conftest import (
    E2EClient,
    get_tools_called,
    today_str,
)
from .test_messages import MESSAGES


@pytest.mark.asyncio
async def test_33_dual_pet_daily(e2e_debug_with_two_pets: E2EClient):
    """§33: Dual pet daily — per-pet records, joint record, per-pet query, per-pet reminders."""
    e2e = e2e_debug_with_two_pets
    msgs = MESSAGES["33_seq"]["zh"]

    # ── 33.1  小维 ate dog food ──
    r1 = await e2e.chat(msgs[0])
    assert r1.error is None, f"33.1 error: {r1.error}\n{r1.dump()}"
    assert r1.has_card("record"), f"33.1: Expected record card.\n{r1.dump()}"
    card1 = r1.first_card("record")
    pet_names_1 = card1.get("pet_name", "") or card1.get("pet_names", "")
    pet_str_1 = str(pet_names_1)
    assert "小维" in pet_str_1, f"33.1: Record should mention 小维, got {pet_str_1}.\n{r1.dump()}"
    assert "花花" not in pet_str_1, f"33.1: Record should NOT mention 花花, got {pet_str_1}.\n{r1.dump()}"

    # ── 33.2  花花 ate cat food ──
    r2 = await e2e.chat(msgs[1])
    assert r2.error is None, f"33.2 error: {r2.error}\n{r2.dump()}"
    assert r2.has_card("record"), f"33.2: Expected record card.\n{r2.dump()}"
    card2 = r2.first_card("record")
    pet_names_2 = card2.get("pet_name", "") or card2.get("pet_names", "")
    pet_str_2 = str(pet_names_2)
    assert "花花" in pet_str_2, f"33.2: Record should mention 花花, got {pet_str_2}.\n{r2.dump()}"
    assert "小维" not in pet_str_2, f"33.2: Record should NOT mention 小维, got {pet_str_2}.\n{r2.dump()}"

    # ── 33.3  Both pets went to park ──
    r3 = await e2e.chat(msgs[2])
    assert r3.error is None, f"33.3 error: {r3.error}\n{r3.dump()}"
    # Could be one record with both pets or two separate records
    all_record_cards = r3.all_cards("record")
    all_pet_text = " ".join(
        str(c.get("pet_name", "")) + str(c.get("pet_names", ""))
        for c in all_record_cards
    )
    assert "小维" in all_pet_text, f"33.3: Should mention 小维.\n{r3.dump()}"
    assert "花花" in all_pet_text, f"33.3: Should mention 花花.\n{r3.dump()}"

    # ── 33.4  小维 vomited — abnormal, only 小维 ──
    r4 = await e2e.chat(msgs[3])
    assert r4.error is None, f"33.4 error: {r4.error}\n{r4.dump()}"
    assert r4.has_card("record"), f"33.4: Expected record card.\n{r4.dump()}"
    card4 = r4.first_card("record")
    assert card4.get("category") == "abnormal", (
        f"33.4: Expected category 'abnormal', got '{card4.get('category')}'.\n{r4.dump()}"
    )
    pet_str_4 = str(card4.get("pet_name", "")) + str(card4.get("pet_names", ""))
    assert "小维" in pet_str_4, f"33.4: Should mention 小维.\n{r4.dump()}"
    assert "花花" not in pet_str_4, f"33.4: Should NOT mention 花花.\n{r4.dump()}"

    # ── 33.5  Query 花花's recent diet ──
    r5 = await e2e.chat(msgs[4])
    assert r5.error is None, f"33.5 error: {r5.error}\n{r5.dump()}"
    assert "猫粮" in r5.text or "cat food" in r5.text.lower(), (
        f"33.5: Response should mention 猫粮/cat food.\n{r5.dump()}"
    )
    assert "狗粮" not in r5.text, (
        f"33.5: Response should NOT mention 狗粮 (that's 小维's food).\n{r5.dump()}"
    )

    # ── 33.6  Reminder for 小维: medicine tomorrow ──
    r6 = await e2e.chat(msgs[5])
    assert r6.error is None, f"33.6 error: {r6.error}\n{r6.dump()}"
    # Reminders are now merged into calendar events (record cards with reminder_at)
    assert r6.has_card("record") or "提醒" in r6.text or "remind" in r6.text.lower(), (
        f"33.6: Expected record card or reminder mention.\n{r6.dump()}"
    )
    if r6.has_card("record"):
        reminder6 = r6.first_card("record")
        reminder_pet_6 = str(reminder6.get("pet_name", "")) + str(reminder6.get("pet_names", ""))
        assert "小维" in reminder_pet_6, f"33.6: Reminder should be for 小维.\n{r6.dump()}"

    # ── 33.7  花花 also needs medicine ──
    r7 = await e2e.chat(msgs[6])
    assert r7.error is None, f"33.7 error: {r7.error}\n{r7.dump()}"
    # Reminders are now merged into calendar events (record cards with reminder_at)
    assert r7.has_card("record") or "提醒" in r7.text or "remind" in r7.text.lower(), (
        f"33.7: Expected record card or reminder mention.\n{r7.dump()}"
    )
    if r7.has_card("record"):
        reminder7 = r7.first_card("record")
        reminder_pet_7 = str(reminder7.get("pet_name", "")) + str(reminder7.get("pet_names", ""))
        assert "花花" in reminder_pet_7, f"33.7: Reminder should be for 花花.\n{r7.dump()}"
