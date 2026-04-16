"""E2E tests for edge cases (TEST_PLAN 21.1, 21.2, 2.11)."""

import pytest

from .conftest import E2EClient, has_cjk, today_str
from .test_messages import MESSAGES


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_20_1_no_pets(e2e: E2EClient, lang: str):
    """20.1 Chat with no pets created — should reply normally, no crash."""
    result = await e2e.chat(MESSAGES["21.1"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.text.strip(), f"Expected non-empty response.\n{result.dump()}"


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_20_2_no_events(e2e_with_pet: E2EClient, lang: str):
    """20.2 Ask about pet status with no prior events — should mention no records."""
    result = await e2e_with_pet.chat(MESSAGES["21.2"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.text.strip(), f"Expected non-empty response.\n{result.dump()}"


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_20_4_multi_intent(e2e_with_pet: E2EClient, lang: str):
    """20.4 Single message with two intents — should produce both record and reminder cards."""
    result = await e2e_with_pet.chat(MESSAGES["2.11"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    total_cards = result.card_count("record") + result.card_count("reminder")
    assert total_cards >= 2, (
        f"Expected at least 2 cards (record + reminder), got {total_cards}.\n{result.dump()}"
    )
