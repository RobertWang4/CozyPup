"""E2E test for long conversation context preservation (TEST_PLAN section 39).

Sends 12 messages sequentially to test that the LLM retains information
from early turns even after many interactions (context compression should
have kicked in). Steps 39.10-39.12 are the key recall assertions.
"""

import pytest

from .conftest import E2EClient, get_tools_called, today_str
from .test_messages import MESSAGES


MOCK_LOCATION = {"latitude": 39.9042, "longitude": 116.4074}  # Beijing


@pytest.mark.asyncio
async def test_39_long_context_preservation(e2e_debug_with_pet: E2EClient):
    """section 39: 12-step long conversation — verify context recall after many turns."""
    e2e = e2e_debug_with_pet
    msgs = MESSAGES["39_seq"]["zh"]
    assert len(msgs) == 12, f"Expected 12 messages in 39_seq, got {len(msgs)}"

    # ── 39.1  Record: ate dog food ──
    r1 = await e2e.chat(msgs[0])
    assert r1.error is None, f"39.1 error: {r1.error}\n{r1.dump()}"
    assert r1.has_card("record"), f"39.1: Expected record card.\n{r1.dump()}"

    # ── 39.2  Record: afternoon walk ──
    r2 = await e2e.chat(msgs[1])
    assert r2.error is None, f"39.2 error: {r2.error}\n{r2.dump()}"
    assert r2.has_card("record"), f"39.2: Expected record card.\n{r2.dump()}"

    # ── 39.3  Record: evening bath ──
    r3 = await e2e.chat(msgs[2])
    assert r3.error is None, f"39.3 error: {r3.error}\n{r3.dump()}"
    assert r3.has_card("record"), f"39.3: Expected record card.\n{r3.dump()}"

    # ── 39.4  Update pet weight to 30kg ──
    r4 = await e2e.chat(msgs[3])
    assert r4.error is None, f"39.4 error: {r4.error}\n{r4.dump()}"
    tools4 = get_tools_called(r4)
    assert "update_pet" in tools4, (
        f"39.4: Expected update_pet tool, got {tools4}.\n{r4.dump()}"
    )
    # Verify weight updated via API
    pets = await e2e.get_pets()
    assert any(
        p.get("weight") == 30 or p.get("weight") == 30.0
        for p in pets
    ), f"39.4: Expected pet weight=30, got weights={[p.get('weight') for p in pets]}.\n{r4.dump()}"

    # ── 39.5  Record: spent 50 on collar ──
    r5 = await e2e.chat(msgs[4])
    assert r5.error is None, f"39.5 error: {r5.error}\n{r5.dump()}"
    assert r5.has_card("record"), f"39.5: Expected record card.\n{r5.dump()}"

    # ── 39.6  Reminder: vaccination next week ──
    r6 = await e2e.chat(msgs[5])
    assert r6.error is None, f"39.6 error: {r6.error}\n{r6.dump()}"
    assert r6.has_card("reminder"), f"39.6: Expected reminder card.\n{r6.dump()}"

    # ── 39.7  Daily task: walk dog twice a day ──
    r7 = await e2e.chat(msgs[6])
    assert r7.error is None, f"39.7 error: {r7.error}\n{r7.dump()}"
    assert r7.has_card("daily_task_created"), (
        f"39.7: Expected daily_task_created card.\n{r7.dump()}"
    )

    # ── 39.8  Profile update: allergic to chicken ──
    r8 = await e2e.chat(msgs[7])
    assert r8.error is None, f"39.8 error: {r8.error}\n{r8.dump()}"
    tools8 = get_tools_called(r8)
    assert "update_pet" in tools8, (
        f"39.8: Expected update_pet tool for allergy update, got {tools8}.\n{r8.dump()}"
    )

    # ── 39.9  Places search: dog park nearby (with location) ──
    r9 = await e2e.chat(msgs[8], location=MOCK_LOCATION)
    assert r9.error is None, f"39.9 error: {r9.error}\n{r9.dump()}"
    assert r9.has_card("place_card"), (
        f"39.9: Expected place_card.\n{r9.dump()}"
    )

    # ═══════════════════════════════════════════════════════════════════
    # Key recall assertions — test context preserved after 9+ turns
    # ═══════════════════════════════════════════════════════════════════

    # ── 39.10  Recall: what was recorded today? ──
    r10 = await e2e.chat(msgs[9])
    assert r10.error is None, f"39.10 error: {r10.error}\n{r10.dump()}"
    text10 = r10.text.lower()
    # Should mention at least 2 of: dog food, walk, bath, collar
    recall_keywords_zh = ["狗粮", "散步", "洗澡", "项圈"]
    recall_keywords_en = ["food", "walk", "bath", "collar"]
    matched_zh = sum(1 for kw in recall_keywords_zh if kw in r10.text)
    matched_en = sum(1 for kw in recall_keywords_en if kw in text10)
    matched = max(matched_zh, matched_en)
    assert matched >= 2, (
        f"39.10: Expected at least 2 of {recall_keywords_zh} in reply, "
        f"matched {matched}.\n{r10.dump()}"
    )

    # ── 39.11  Recall: how much does Weiwei weigh? ──
    r11 = await e2e.chat(msgs[10])
    assert r11.error is None, f"39.11 error: {r11.error}\n{r11.dump()}"
    assert "30" in r11.text, (
        f"39.11: Expected '30' (kg) in reply.\n{r11.dump()}"
    )

    # ── 39.12  Recall: what was the first record? ──
    r12 = await e2e.chat(msgs[11])
    assert r12.error is None, f"39.12 error: {r12.error}\n{r12.dump()}"
    text12 = r12.text.lower()
    assert "狗粮" in r12.text or "food" in text12 or "粮" in r12.text, (
        f"39.12: Expected mention of dog food (first record) in reply.\n{r12.dump()}"
    )
