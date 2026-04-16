"""E2E tests for language switching (TEST_PLAN 13.1-13.2)."""

import pytest

from .conftest import E2EClient, has_cjk, today_str
from .test_messages import MESSAGES


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_12_1_switch_to_english(e2e: E2EClient, lang: str):
    """12.1 Switch to English — should return set_language card with 'en'."""
    result = await e2e.chat(MESSAGES["13.1"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("set_language"), (
        f"Expected set_language card.\n{result.dump()}"
    )
    card = result.first_card("set_language")
    assert "en" in card.get("language", ""), (
        f"Expected language to contain 'en', got: {card.get('language')}\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_12_2_switch_to_chinese(e2e: E2EClient, lang: str):
    """12.2 Switch to Chinese — should return set_language card with 'zh'."""
    result = await e2e.chat(MESSAGES["13.2"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("set_language"), (
        f"Expected set_language card.\n{result.dump()}"
    )
    card = result.first_card("set_language")
    assert "zh" in card.get("language", ""), (
        f"Expected language to contain 'zh', got: {card.get('language')}\n{result.dump()}"
    )
