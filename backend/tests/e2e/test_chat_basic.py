"""E2E tests for basic chat functionality (TEST_PLAN 1.1-1.3)."""

import pytest

from .conftest import E2EClient, has_cjk
from .test_messages import MESSAGES


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_1_1_greeting(e2e: E2EClient, lang: str):
    """1.1 Simple greeting — should get a text reply, no cards."""
    result = await e2e.chat(MESSAGES["1.1"][lang])
    assert result.error is None, f"Chat error: {result.error}"
    assert result.text.strip(), f"Empty response.\n{result.dump()}"
    assert len(result.cards) == 0, f"Expected no cards for greeting.\n{result.dump()}"


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_1_2_hi(e2e: E2EClient, lang: str):
    """1.2 'hi' message — zh should get Chinese response."""
    result = await e2e.chat(MESSAGES["1.2"][lang])
    assert result.error is None, f"Chat error: {result.error}"
    assert result.text.strip(), f"Empty response.\n{result.dump()}"
    if lang == "zh":
        assert has_cjk(result.text), (
            f"Expected Chinese characters in zh response.\n{result.dump()}"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_1_3_rapid_fire(e2e: E2EClient, lang: str):
    """1.3 Three messages in sequence — all should get non-empty replies."""
    results = await e2e.chat_sequence(MESSAGES["1.3_seq"][lang])
    assert len(results) == 3, f"Expected 3 results, got {len(results)}"
    for i, result in enumerate(results):
        assert result.error is None, (
            f"Message {i} error: {result.error}\n{result.dump()}"
        )
        assert result.text.strip(), (
            f"Message {i} got empty response.\n{result.dump()}"
        )
