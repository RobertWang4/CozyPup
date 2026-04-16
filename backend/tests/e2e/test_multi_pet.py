"""E2E tests for multi-pet scenarios (TEST_PLAN 14.1-14.5)."""

import pytest

from .conftest import E2EClient, has_cjk, today_str
from .test_messages import MESSAGES


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_13_1_ambiguous_pet(e2e_with_two_pets: E2EClient, lang: str):
    """13.1 Two pets, no name specified — LLM should ask which pet."""
    result = await e2e_with_two_pets.chat(MESSAGES["14.1"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    # LLM should ask a clarifying question
    assert "?" in result.text or "\uff1f" in result.text or not result.has_card("record"), (
        f"Expected LLM to ask which pet, but got a direct record.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_13_2_both_pets_walk(e2e_with_two_pets: E2EClient, lang: str):
    """13.2 Both pets went for a walk — should create event(s)."""
    result = await e2e_with_two_pets.chat(MESSAGES["14.2"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    # Should create at least one record card (could be one per pet or a combined one)
    assert result.has_card("record"), (
        f"Expected record card(s) for walk event.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_13_3_single_pet_auto_assign(e2e_with_pet: E2EClient, lang: str):
    """13.3 Single pet, no name specified — should auto-assign to the only pet."""
    result = await e2e_with_pet.chat(MESSAGES["14.3"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("record"), (
        f"Expected record card (auto-assigned to single pet).\n{result.dump()}"
    )
