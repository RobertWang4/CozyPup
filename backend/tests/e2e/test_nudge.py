"""E2E tests for nudge mechanism (TEST_PLAN §23.1-23.3).

Verifies that the agent actually calls the appropriate tool rather than
just replying with text:
- Location query with coordinates -> must call search_places
- Language switch request -> must call set_language
- Emergency report -> must trigger emergency SSE event
"""

import pytest

from .conftest import E2EClient, get_tools_called
from .test_messages import MESSAGES


# ═══════════════════════════════════════════════════════════════════════════
# 23.1 — "附近有宠物医院吗" with location → search_places tool called
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_23_1_nearby_hospital_calls_search_places(e2e_debug_with_pet: E2EClient):
    """23.1 '附近有宠物医院吗' with location -> must call search_places tool."""
    e2e = e2e_debug_with_pet

    result = await e2e.chat(
        MESSAGES["23.1"]["zh"],
        location={"lat": 45.4215, "lng": -75.6972},
    )
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"

    tools = get_tools_called(result)
    assert "search_places" in tools, (
        f"Expected search_places in tools_called (must call tool, not just reply text). "
        f"Got: {tools}\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 23.2 — "switch to English" → set_language tool called
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_23_2_switch_language_calls_set_language(e2e_debug_with_pet: E2EClient):
    """23.2 'switch to English' -> must call set_language tool."""
    e2e = e2e_debug_with_pet

    result = await e2e.chat(MESSAGES["23.2"]["zh"])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"

    tools = get_tools_called(result)
    assert "set_language" in tools, (
        f"Expected set_language in tools_called (must call tool, not just reply text). "
        f"Got: {tools}\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 23.3 — "小维中毒了！" → emergency event triggered
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_23_3_poisoning_triggers_emergency(e2e_debug_with_pet: E2EClient):
    """23.3 '小维中毒了！' -> emergency SSE event must fire (not just text advice)."""
    e2e = e2e_debug_with_pet

    result = await e2e.chat(MESSAGES["23.3"]["zh"])
    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.emergency is not None, (
        f"Expected an emergency SSE event for poisoning report. "
        f"Got no emergency event.\n{result.dump()}"
    )
