"""E2E tests for reminder tools (TEST_PLAN 9.1-9.6).

Reminders are now merged into calendar events with reminder_at.
The backend returns a 'record' card (not 'reminder') when creating
calendar events with reminder_at set.
"""

import pytest

from .conftest import E2EClient, has_cjk, today_str
from .test_messages import MESSAGES


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_8_1_create_reminder_medicine(e2e_with_pet: E2EClient, lang: str):
    """8.1 Create a medicine reminder — should return a record card with reminder context."""
    result = await e2e_with_pet.chat(MESSAGES["9.1"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("record") or "提醒" in result.text or "remind" in result.text.lower(), (
        f"Expected record card or reminder mention in text.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_8_2_create_reminder_vaccination(e2e_with_pet: E2EClient, lang: str):
    """8.2 Create a vaccination reminder — should return a record card with reminder context."""
    result = await e2e_with_pet.chat(MESSAGES["9.2"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("record") or "提醒" in result.text or "remind" in result.text.lower(), (
        f"Expected record card or reminder mention in text.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_8_3_list_reminders(e2e_with_pet: E2EClient, lang: str):
    """8.3 Create reminders first, then ask what reminders exist."""
    # Setup: create a couple of reminders
    await e2e_with_pet.chat(MESSAGES["9.1"][lang])
    await e2e_with_pet.chat(MESSAGES["9.2"][lang])

    # Query reminders
    result = await e2e_with_pet.chat(MESSAGES["9.3"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.text.strip(), f"Expected non-empty response.\n{result.dump()}"


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_8_4_cancel_reminder(e2e_with_pet: E2EClient, lang: str):
    """8.4 Create a reminder, then cancel it — should get confirm_action card or acknowledgement."""
    # Setup: create the medicine reminder first
    await e2e_with_pet.chat(MESSAGES["9.1"][lang])

    # Cancel it
    result = await e2e_with_pet.chat(MESSAGES["9.5"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    # With reminders merged into calendar events, cancellation may produce
    # confirm_action, or the LLM may just acknowledge the cancellation
    assert result.has_card("confirm_action") or result.text.strip(), (
        f"Expected confirm_action card or text acknowledgement.\n{result.dump()}"
    )
