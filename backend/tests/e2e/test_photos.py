"""E2E tests for photo upload, vision analysis, and removal (TEST_PLAN §7)."""

import pytest

from .conftest import E2EClient, get_tools_called, load_test_image, today_str
from .test_messages import MESSAGES


# ═══════════════════════════════════════════════════════════════════════════
# 7a. Photo + new event (auto-attach)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.xfail(reason="LLM sometimes asks clarifying question instead of recording with photo")
async def test_7_1_photo_with_new_event(e2e_debug_with_pet: E2EClient):
    """7.1 Send image + '记录一下小维今天' → record card, event photos non-empty."""
    e2e = e2e_debug_with_pet
    img = load_test_image()
    result = await e2e.chat(MESSAGES["7.1"]["zh"], images=[img])

    assert result.error is None, f"Chat error: {result.error}"
    assert result.has_card("record"), (
        f"Expected a record card.\n{result.dump()}"
    )

    # Verify photo attached to the event
    events = await e2e.get_events(date_str=today_str())
    photo_events = [e for e in events if e.get("photos")]
    assert photo_events, (
        f"No events with photos found for today.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.xfail(reason="LLM sometimes asks clarifying question instead of recording with photo")
async def test_7_2_two_photos_with_new_event(e2e_debug_with_pet: E2EClient):
    """7.2 Send 2 images + '记一下' → record card, event photos length >= 2."""
    e2e = e2e_debug_with_pet
    img1 = load_test_image()
    img2 = load_test_image()
    result = await e2e.chat(MESSAGES["7.2"]["zh"], images=[img1, img2])

    assert result.error is None, f"Chat error: {result.error}"
    assert result.has_card("record"), (
        f"Expected a record card.\n{result.dump()}"
    )

    # Verify at least 2 photos attached
    events = await e2e.get_events(date_str=today_str())
    photo_events = [e for e in events if e.get("photos")]
    assert photo_events, (
        f"No events with photos found for today.\n{result.dump()}"
    )
    max_photos = max(len(e["photos"]) for e in photo_events)
    assert max_photos >= 2, (
        f"Expected >= 2 photos on event, got {max_photos}.\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7b. Upload to existing event (upload_event_photo)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_7_3_upload_photo_to_existing_event_zh(e2e_debug_with_pet: E2EClient):
    """7.3 Create event first, then send image + '把这张照片加到刚才的记录' → upload_event_photo."""
    e2e = e2e_debug_with_pet

    # Step 1: create an event via chat
    setup = await e2e.chat("小维今天去公园了")
    assert setup.error is None, f"Setup chat error: {setup.error}"
    assert setup.has_card("record"), (
        f"Setup: expected record card for park event.\n{setup.dump()}"
    )

    # Step 2: upload photo to that event
    img = load_test_image()
    result = await e2e.chat(MESSAGES["7.3"]["zh"], images=[img])
    assert result.error is None, f"Chat error: {result.error}"

    tools = get_tools_called(result)
    assert "upload_event_photo" in tools, (
        f"Expected upload_event_photo in tools_called, got {tools}.\n{result.dump()}"
    )

    # Verify photo attached via API
    events = await e2e.get_events(date_str=today_str())
    photo_events = [e for e in events if e.get("photos")]
    assert photo_events, (
        f"No events with photos found after upload.\n{result.dump()}"
    )


@pytest.mark.asyncio
async def test_7_4_upload_photo_to_existing_event_en(e2e_debug_with_pet: E2EClient):
    """7.4 Same as 7.3 but English: 'Add this to the event' → upload_event_photo."""
    e2e = e2e_debug_with_pet

    # Step 1: create an event via chat
    setup = await e2e.chat("小维今天去公园了")
    assert setup.error is None, f"Setup chat error: {setup.error}"
    assert setup.has_card("record"), (
        f"Setup: expected record card for park event.\n{setup.dump()}"
    )

    # Step 2: upload photo to that event (English)
    img = load_test_image()
    result = await e2e.chat(MESSAGES["7.4"]["en"], images=[img])
    assert result.error is None, f"Chat error: {result.error}"

    tools = get_tools_called(result)
    assert "upload_event_photo" in tools, (
        f"Expected upload_event_photo in tools_called, got {tools}.\n{result.dump()}"
    )

    # Verify photo attached via API
    events = await e2e.get_events(date_str=today_str())
    photo_events = [e for e in events if e.get("photos")]
    assert photo_events, (
        f"No events with photos found after upload.\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7c. Cross-turn image fallback (recent_image_urls)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_7_5_cross_turn_photo_attached_to_event(e2e_debug_with_pet: E2EClient):
    """7.5 Turn 1: image + '小维今天去公园了'. Turn 2: '记录一下' (no image) → event has photo."""
    e2e = e2e_debug_with_pet
    img = load_test_image()

    # Turn 1: send image with a casual message (agent may or may not record)
    turn1 = await e2e.chat("小维今天去公园了", images=[img])
    assert turn1.error is None, f"Turn 1 error: {turn1.error}"

    # Turn 2: ask to record (no image) — should pick up photo from turn 1
    result = await e2e.chat(MESSAGES["7.5"]["zh"])
    assert result.error is None, f"Turn 2 error: {result.error}"

    # Verify at least one event today has photos (from either turn)
    events = await e2e.get_events(date_str=today_str())
    photo_events = [e for e in events if e.get("photos")]
    assert photo_events, (
        f"No events with photos found — cross-turn fallback failed.\n"
        f"Turn 1:\n{turn1.dump()}\nTurn 2:\n{result.dump()}"
    )


@pytest.mark.asyncio
async def test_7_6_cross_turn_vision_from_history(e2e_debug_with_pet: E2EClient):
    """7.6 Turn 1: image + '小维真可爱'. Turn 2: '刚才那张照片是什么品种？' → request_images."""
    e2e = e2e_debug_with_pet
    img = load_test_image()

    # Turn 1: send image with casual comment
    turn1 = await e2e.chat("小维真可爱", images=[img])
    assert turn1.error is None, f"Turn 1 error: {turn1.error}"

    # Turn 2: ask about the photo from turn 1 (no image this turn)
    result = await e2e.chat(MESSAGES["7.6"]["zh"])
    assert result.error is None, f"Turn 2 error: {result.error}"

    tools = get_tools_called(result)
    assert "request_images" in tools, (
        f"Expected request_images in tools_called, got {tools}.\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7d. Vision analysis (request_images)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_7_7_vision_breed_identification(e2e_debug_with_pet: E2EClient):
    """7.7 Send image + '这是什么品种？' → request_images called, text non-empty."""
    e2e = e2e_debug_with_pet
    img = load_test_image()
    result = await e2e.chat(MESSAGES["7.7"]["zh"], images=[img])

    assert result.error is None, f"Chat error: {result.error}"

    tools = get_tools_called(result)
    assert "request_images" in tools, (
        f"Expected request_images in tools_called, got {tools}.\n{result.dump()}"
    )
    assert result.text.strip(), (
        f"Expected non-empty text response for breed analysis.\n{result.dump()}"
    )


@pytest.mark.asyncio
async def test_7_8_vision_health_check(e2e_debug_with_pet: E2EClient):
    """7.8 Send image + '看看这只狗有什么问题吗？' → request_images called."""
    e2e = e2e_debug_with_pet
    img = load_test_image()
    result = await e2e.chat(MESSAGES["7.8"]["zh"], images=[img])

    assert result.error is None, f"Chat error: {result.error}"

    tools = get_tools_called(result)
    assert "request_images" in tools, (
        f"Expected request_images in tools_called, got {tools}.\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7e. Remove photo (remove_event_photo)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.xfail(reason="LLM sometimes asks clarifying question instead of recording with photo")
async def test_7_9_remove_event_photo(e2e_debug_with_pet: E2EClient):
    """7.9 Create event with photo, then '把那条记录的照片删掉' → remove_event_photo called."""
    e2e = e2e_debug_with_pet
    img = load_test_image()

    # Step 1: create an event with a photo attached
    setup = await e2e.chat(MESSAGES["7.1"]["zh"], images=[img])
    assert setup.error is None, f"Setup error: {setup.error}"
    assert setup.has_card("record"), (
        f"Setup: expected record card.\n{setup.dump()}"
    )

    # Verify photo exists before removal
    events_before = await e2e.get_events(date_str=today_str())
    photo_events_before = [e for e in events_before if e.get("photos")]
    assert photo_events_before, (
        f"Setup: no event with photos found before removal.\n{setup.dump()}"
    )

    # Step 2: ask to remove the photo
    result = await e2e.chat(MESSAGES["7.9"]["zh"])
    assert result.error is None, f"Chat error: {result.error}"

    tools = get_tools_called(result)
    assert "remove_event_photo" in tools, (
        f"Expected remove_event_photo in tools_called, got {tools}.\n{result.dump()}"
    )
