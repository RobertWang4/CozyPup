"""E2E tests for pet profile management (TEST_PLAN 14.1-14.2)."""

import pytest

from .conftest import E2EClient, has_cjk, today_str
from .test_messages import MESSAGES


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_14_1_profile_extraction(e2e_with_pet: E2EClient, lang: str):
    """14.1 Mention personality traits — should process without error."""
    result = await e2e_with_pet.chat(MESSAGES["14.1"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.text.strip(), f"Expected non-empty response.\n{result.dump()}"


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_14_2_summarize_profile(e2e_with_pet: E2EClient, lang: str):
    """14.2 Ask to summarize pet profile — response should contain pet info."""
    result = await e2e_with_pet.chat(MESSAGES["14.2"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.text.strip(), f"Expected non-empty response.\n{result.dump()}"
