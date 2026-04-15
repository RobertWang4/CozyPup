"""E2E tests for photo multi-turn interaction flow (TEST_PLAN §32).

5-step sequential test: upload photo with record → request images for
breed analysis → set pet avatar → add photo to existing record →
remove photo.
"""

import pytest

from .conftest import (
    E2EClient,
    get_tools_called,
    load_test_image,
    today_str,
)
from .test_messages import MESSAGES


@pytest.mark.asyncio
async def test_32_photo_multiturn(e2e_debug_with_pet: E2EClient):
    """§32: Photo multi-turn — record+photo → breed query → avatar → add photo → remove photo."""
    e2e = e2e_debug_with_pet
    msgs = MESSAGES["32_seq"]["zh"]
    img = load_test_image()

    # ── 32.1  Send image + record ──
    r1 = await e2e.chat(msgs[0], images=[img])
    assert r1.error is None, f"32.1 error: {r1.error}\n{r1.dump()}"
    assert r1.has_card("record"), f"32.1: Expected record card.\n{r1.dump()}"
    # Verify event has photos
    events = await e2e.get_events(date_str=today_str())
    photo_events = [ev for ev in events if ev.get("photos")]
    assert photo_events, f"32.1: Expected event with photos.\n{r1.dump()}"

    # ── 32.2  Ask about breed (no image, references previous) ──
    r2 = await e2e.chat(msgs[1])
    assert r2.error is None, f"32.2 error: {r2.error}\n{r2.dump()}"
    tools2 = get_tools_called(r2)
    assert "request_images" in tools2, (
        f"32.2: Expected request_images tool call, got {tools2}.\n{r2.dump()}"
    )
    assert r2.text, f"32.2: Expected non-empty text response.\n{r2.dump()}"

    # ── 32.3  Use photo as pet avatar ──
    r3 = await e2e.chat(msgs[2])
    assert r3.error is None, f"32.3 error: {r3.error}\n{r3.dump()}"
    tools3 = get_tools_called(r3)
    assert "set_pet_avatar" in tools3, (
        f"32.3: Expected set_pet_avatar tool call, got {tools3}.\n{r3.dump()}"
    )
    # Verify avatar_url is set on pet
    pets = await e2e.get_pets()
    pet = next((p for p in pets if p["name"] == "小维"), None)
    assert pet and pet.get("avatar_url"), (
        f"32.3: Expected pet avatar_url to be set.\n{r3.dump()}"
    )

    # ── 32.4  Add new photo to earlier record ──
    img2 = load_test_image()
    r4 = await e2e.chat(msgs[3], images=[img2])
    assert r4.error is None, f"32.4 error: {r4.error}\n{r4.dump()}"
    tools4 = get_tools_called(r4)
    assert "upload_event_photo" in tools4, (
        f"32.4: Expected upload_event_photo tool call, got {tools4}.\n{r4.dump()}"
    )

    # ── 32.5  Remove first photo ──
    r5 = await e2e.chat(msgs[4])
    assert r5.error is None, f"32.5 error: {r5.error}\n{r5.dump()}"
    tools5 = get_tools_called(r5)
    assert "remove_event_photo" in tools5, (
        f"32.5: Expected remove_event_photo tool call, got {tools5}.\n{r5.dump()}"
    )
