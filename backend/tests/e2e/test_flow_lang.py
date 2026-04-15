"""E2E tests for language switch operations flow (TEST_PLAN §36).

6-step sequential test: switch to English → record in English →
delete record (English confirm) → switch to Chinese → record in Chinese →
delete record (Chinese confirm).
"""

import pytest

from .conftest import (
    E2EClient,
    get_tools_called,
    has_cjk,
)
from .test_messages import MESSAGES


@pytest.mark.asyncio
async def test_36_language_switch(e2e_debug_with_pet: E2EClient):
    """§36: Language switch — EN record + delete → ZH record + delete, verify confirm language."""
    e2e = e2e_debug_with_pet
    msgs = MESSAGES["36_seq"]["zh"]

    # ── 36.1  Switch to English ──
    r1 = await e2e.chat(msgs[0])
    assert r1.error is None, f"36.1 error: {r1.error}\n{r1.dump()}"
    tools1 = get_tools_called(r1)
    assert "set_language" in tools1, (
        f"36.1: Expected set_language tool call, got {tools1}.\n{r1.dump()}"
    )

    # ── 36.2  Record in English ──
    r2 = await e2e.chat(msgs[1], language="en")
    assert r2.error is None, f"36.2 error: {r2.error}\n{r2.dump()}"
    assert r2.has_card("record"), f"36.2: Expected record card.\n{r2.dump()}"

    # ── 36.3  Delete that record — English confirm ──
    r3 = await e2e.chat(msgs[2], language="en")
    assert r3.error is None, f"36.3 error: {r3.error}\n{r3.dump()}"
    assert r3.has_card("confirm_action"), (
        f"36.3: Expected confirm_action card.\n{r3.dump()}"
    )
    confirm_card_3 = r3.first_card("confirm_action")
    desc_3 = confirm_card_3.get("description", "") or confirm_card_3.get("message", "")
    assert not has_cjk(desc_3), (
        f"36.3: English confirm description should not contain CJK chars. Got: {desc_3}\n{r3.dump()}"
    )

    # ── 36.4  Switch to Chinese ──
    r4 = await e2e.chat(msgs[3])
    assert r4.error is None, f"36.4 error: {r4.error}\n{r4.dump()}"
    tools4 = get_tools_called(r4)
    assert "set_language" in tools4, (
        f"36.4: Expected set_language tool call, got {tools4}.\n{r4.dump()}"
    )

    # ── 36.5  Record in Chinese ──
    r5 = await e2e.chat(msgs[4], language="zh")
    assert r5.error is None, f"36.5 error: {r5.error}\n{r5.dump()}"
    assert r5.has_card("record"), f"36.5: Expected record card.\n{r5.dump()}"

    # ── 36.6  Delete that record — Chinese confirm ──
    r6 = await e2e.chat(msgs[5], language="zh")
    assert r6.error is None, f"36.6 error: {r6.error}\n{r6.dump()}"
    assert r6.has_card("confirm_action"), (
        f"36.6: Expected confirm_action card.\n{r6.dump()}"
    )
    confirm_card_6 = r6.first_card("confirm_action")
    desc_6 = confirm_card_6.get("description", "") or confirm_card_6.get("message", "")
    assert has_cjk(desc_6), (
        f"36.6: Chinese confirm description should contain CJK chars. Got: {desc_6}\n{r6.dump()}"
    )
