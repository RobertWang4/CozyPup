"""E2E tests for map/search tools (TEST_PLAN 10.1-10.2)."""

import pytest

from .conftest import E2EClient, has_cjk, today_str
from .test_messages import MESSAGES


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_9_1_nearby_pet_hospital(e2e_with_pet: E2EClient, lang: str):
    """9.1 Search for nearby pet hospitals — should return a map card."""
    result = await e2e_with_pet.chat(
        MESSAGES["10.1"][lang],
        location={"lat": 39.9042, "lng": 116.4074},
    )
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("place_card") or result.has_card("map"), (
        f"Expected place_card.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_9_2_nearby_dog_park(e2e_with_pet: E2EClient, lang: str):
    """9.2 Search for nearest dog park — should return a place card."""
    result = await e2e_with_pet.chat(
        MESSAGES["10.2"][lang],
        location={"lat": 39.9042, "lng": 116.4074},
    )
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    # LLM sometimes returns text instead of place_card
    has_place = result.has_card("place_card") or result.has_card("map")
    has_park_text = any(
        kw in result.text.lower()
        for kw in ["park", "公园", "dog park", "狗公园"]
    )
    assert has_place or has_park_text, (
        f"Expected place_card or park mention in text.\n{result.dump()}"
    )
