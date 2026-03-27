"""E2E tests for emergency detection (TEST_PLAN 11.1-11.3)."""

import pytest

from .conftest import E2EClient, has_cjk, today_str
from .test_messages import MESSAGES


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_11_1_seizure_emergency(e2e_with_pet: E2EClient, lang: str):
    """11.1 Cat having seizures — should trigger emergency event."""
    result = await e2e_with_pet.chat(MESSAGES["11.1"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.emergency is not None, (
        f"Expected emergency event for seizure report.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_11_2_poisoning_emergency(e2e_with_pet: E2EClient, lang: str):
    """11.2 Pet poisoned and dying — should trigger emergency event."""
    result = await e2e_with_pet.chat(MESSAGES["11.2"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.emergency is not None, (
        f"Expected emergency event for poisoning report.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_11_3_history_not_emergency(e2e_with_pet: E2EClient, lang: str):
    """11.3 Asking about past poisoning — should NOT trigger emergency."""
    result = await e2e_with_pet.chat(MESSAGES["11.3"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.emergency is None, (
        f"Should NOT trigger emergency for history query.\n{result.dump()}"
    )
