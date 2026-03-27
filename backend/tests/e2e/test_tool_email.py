"""E2E tests for email drafting tool (TEST_PLAN 10.1)."""

import pytest

from .conftest import E2EClient, has_cjk, today_str
from .test_messages import MESSAGES


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_10_1_draft_email_to_vet(e2e_with_pet: E2EClient, lang: str):
    """10.1 Draft an email to the vet — should return an email card with subject and body."""
    result = await e2e_with_pet.chat(MESSAGES["10.1"][lang])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("email"), (
        f"Expected email card.\n{result.dump()}"
    )
    card = result.first_card("email")
    assert card.get("subject"), f"Email card missing subject.\n{result.dump()}"
    assert card.get("body"), f"Email card missing body.\n{result.dump()}"
