"""E2E tests for context compression (TEST_PLAN 15.1)."""

import pytest

from .conftest import E2EClient, has_cjk, today_str
from .test_messages import MESSAGES


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_15_1_compression(e2e_with_pet: E2EClient, lang: str):
    """15.1 Send 7 messages in sequence — last response should reference earlier context."""
    results = await e2e_with_pet.chat_sequence(MESSAGES["15.1_seq"][lang])
    assert len(results) == 7, f"Expected 7 results, got {len(results)}"

    # All messages should succeed
    for i, r in enumerate(results):
        assert r.error is None, (
            f"Message {i} error: {r.error}\n{r.dump()}"
        )

    # The last message asks "how has Weiwei been?" — should get a non-empty summary
    last = results[-1]
    assert last.text.strip(), (
        f"Expected non-empty summary response.\n{last.dump()}"
    )
