"""E2E tests for reminder tools (TEST_PLAN 8.1-8.4)."""

import pytest

from .conftest import E2EClient, has_cjk, today_str
from .test_messages import MESSAGES


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_8_1_create_reminder_medicine(e2e_with_pet: E2EClient, lang: str):
    """8.1 Create a medicine reminder — should return a reminder card."""
    result = await e2e_with_pet.chat(MESSAGES["8.1"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("reminder"), (
        f"Expected reminder card.\n{result.dump()}"
    )
    card = result.first_card("reminder")
    assert card.get("reminder_type"), (
        f"Reminder card missing reminder_type.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_8_2_create_reminder_vaccination(e2e_with_pet: E2EClient, lang: str):
    """8.2 Create a vaccination reminder — should return a reminder card."""
    result = await e2e_with_pet.chat(MESSAGES["8.2"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("reminder"), (
        f"Expected reminder card.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_8_3_list_reminders(e2e_with_pet: E2EClient, lang: str):
    """8.3 Create reminders first, then ask what reminders exist."""
    # Setup: create a couple of reminders
    await e2e_with_pet.chat(MESSAGES["8.1"][lang])
    await e2e_with_pet.chat(MESSAGES["8.2"][lang])

    # Query reminders
    result = await e2e_with_pet.chat(MESSAGES["8.3"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.text.strip(), f"Expected non-empty response.\n{result.dump()}"


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_8_4_cancel_reminder(e2e_with_pet: E2EClient, lang: str):
    """8.4 Create a reminder, then cancel it — should get confirm_action card."""
    # Setup: create the medicine reminder first
    await e2e_with_pet.chat(MESSAGES["8.1"][lang])

    # Cancel it
    result = await e2e_with_pet.chat(MESSAGES["8.4"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("confirm_action"), (
        f"Expected confirm_action card for deletion.\n{result.dump()}"
    )
