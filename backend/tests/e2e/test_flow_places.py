"""E2E tests for place exploration multi-turn flow (TEST_PLAN §31).

4-step sequential test: find nearby dog park → get review details →
get directions → record visit with location.
"""

import pytest

from .conftest import (
    E2EClient,
    get_tools_called,
    today_str,
)
from .test_messages import MESSAGES


LOCATION = {"lat": 45.4215, "lng": -75.6972}


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Multi-step LLM flow is non-deterministic — place detail may not be available")
async def test_31_place_exploration(e2e_debug_with_pet: E2EClient):
    """§31: Place exploration — search → detail → directions → record with location."""
    e2e = e2e_debug_with_pet
    msgs = MESSAGES["31_seq"]["zh"]

    # ── 31.1  Find nearby dog parks ──
    r1 = await e2e.chat(msgs[0], location=LOCATION)
    assert r1.error is None, f"31.1 error: {r1.error}\n{r1.dump()}"
    assert r1.has_card("place_card"), f"31.1: Expected place_card.\n{r1.dump()}"

    # ── 31.2  Ask about first result's reviews ──
    r2 = await e2e.chat(msgs[1])
    assert r2.error is None, f"31.2 error: {r2.error}\n{r2.dump()}"
    assert r2.has_card("place_detail"), f"31.2: Expected place_detail card.\n{r2.dump()}"

    # ── 31.3  Get directions ──
    r3 = await e2e.chat(msgs[2])
    assert r3.error is None, f"31.3 error: {r3.error}\n{r3.dump()}"
    assert r3.has_card("directions"), f"31.3: Expected directions card.\n{r3.dump()}"

    # ── 31.4  Record visit with location ──
    r4 = await e2e.chat(msgs[3])
    assert r4.error is None, f"31.4 error: {r4.error}\n{r4.dump()}"
    assert r4.has_card("record"), f"31.4: Expected record card.\n{r4.dump()}"
    # Verify the event has a location set
    events = await e2e.get_events(date_str=today_str())
    located_events = [
        ev for ev in events
        if ev.get("location") or ev.get("place_name") or ev.get("place_id")
    ]
    assert located_events, (
        f"31.4: Expected an event with location/place info, "
        f"got {[{k: ev.get(k) for k in ('location', 'place_name', 'place_id')} for ev in events]}.\n{r4.dump()}"
    )
