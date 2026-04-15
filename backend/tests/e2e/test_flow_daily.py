"""E2E tests for full-day recording flow (TEST_PLAN §26).

Multi-turn sequential test simulating a complete day: feeding, walk, photo,
abnormal event, vet ER search, directions, email, cost query, and summary.
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
async def test_26_full_day_recording(e2e_debug_with_pet: E2EClient):
    """§26: 11-step full day recording — feeding → walk → photo → vomit → ER → directions → email → cost → summary."""
    e2e = e2e_debug_with_pet
    msgs = MESSAGES["26_seq"]["zh"]

    # ── 26.1  Morning feeding ──
    r1 = await e2e.chat(msgs[0])
    assert r1.error is None, f"26.1 error: {r1.error}\n{r1.dump()}"
    assert r1.has_card("record"), f"26.1: Expected record card.\n{r1.dump()}"
    record_card = r1.first_card("record")
    assert record_card.get("category") == "diet", (
        f"26.1: Expected category 'diet', got '{record_card.get('category')}'.\n{r1.dump()}"
    )

    # ── 26.2  Add cost to feeding record ──
    r2 = await e2e.chat(msgs[1])
    assert r2.error is None, f"26.2 error: {r2.error}\n{r2.dump()}"
    tools2 = get_tools_called(r2)
    assert "update_calendar_event" in tools2, (
        f"26.2: Expected update_calendar_event tool, got {tools2}.\n{r2.dump()}"
    )
    # Verify cost was set on the event
    events = await e2e.get_events(date_str=today_str())
    cost_events = [ev for ev in events if ev.get("cost") is not None and ev["cost"] > 0]
    assert any(ev["cost"] == 30 or ev["cost"] == 30.0 for ev in cost_events), (
        f"26.2: Expected an event with cost=30, got costs={[ev.get('cost') for ev in events]}.\n{r2.dump()}"
    )

    # ── 26.3  Park walk ──
    r3 = await e2e.chat(msgs[2])
    assert r3.error is None, f"26.3 error: {r3.error}\n{r3.dump()}"
    assert r3.has_card("record"), f"26.3: Expected record card.\n{r3.dump()}"
    walk_card = r3.first_card("record")
    assert walk_card.get("category") == "daily", (
        f"26.3: Expected category 'daily', got '{walk_card.get('category')}'.\n{r3.dump()}"
    )

    # ── 26.4  Add location to walk ──
    r4 = await e2e.chat(msgs[3])
    assert r4.error is None, f"26.4 error: {r4.error}\n{r4.dump()}"
    tools4 = get_tools_called(r4)
    assert "add_event_location" in tools4, (
        f"26.4: Expected add_event_location tool, got {tools4}.\n{r4.dump()}"
    )

    # ── 26.5  Upload photo ──
    img = load_test_image()
    r5 = await e2e.chat(msgs[4], images=[img])
    assert r5.error is None, f"26.5 error: {r5.error}\n{r5.dump()}"
    tools5 = get_tools_called(r5)
    assert "upload_event_photo" in tools5, (
        f"26.5: Expected upload_event_photo tool, got {tools5}.\n{r5.dump()}"
    )
    # Verify photo attached
    events = await e2e.get_events(date_str=today_str())
    photo_events = [ev for ev in events if ev.get("photos")]
    assert photo_events, f"26.5: No events with photos found.\n{r5.dump()}"

    # ── 26.6  Afternoon vomiting ──
    r6 = await e2e.chat(msgs[5])
    assert r6.error is None, f"26.6 error: {r6.error}\n{r6.dump()}"
    assert r6.has_card("record"), f"26.6: Expected record card.\n{r6.dump()}"
    abnormal_card = r6.first_card("record")
    assert abnormal_card.get("category") == "abnormal", (
        f"26.6: Expected category 'abnormal', got '{abnormal_card.get('category')}'.\n{r6.dump()}"
    )

    # ── 26.7  Search nearby pet ER ──
    r7 = await e2e.chat(
        msgs[6],
        location={"lat": 45.4215, "lng": -75.6972},
    )
    assert r7.error is None, f"26.7 error: {r7.error}\n{r7.dump()}"
    assert r7.has_card("place_card"), (
        f"26.7: Expected place_card.\n{r7.dump()}"
    )

    # ── 26.8  Directions to first result ──
    r8 = await e2e.chat(msgs[7])
    assert r8.error is None, f"26.8 error: {r8.error}\n{r8.dump()}"
    assert r8.has_card("directions"), (
        f"26.8: Expected directions card.\n{r8.dump()}"
    )

    # ── 26.9  Email to vet ──
    r9 = await e2e.chat(msgs[8])
    assert r9.error is None, f"26.9 error: {r9.error}\n{r9.dump()}"
    assert r9.has_card("email"), f"26.9: Expected email card.\n{r9.dump()}"
    email_card = r9.first_card("email")
    body = (email_card.get("body") or "").lower()
    assert "吐" in body or "vomit" in body or "呕" in body, (
        f"26.9: Email body should reference vomiting context.\n{r9.dump()}"
    )

    # ── 26.10  Cost query ──
    r10 = await e2e.chat(msgs[9])
    assert r10.error is None, f"26.10 error: {r10.error}\n{r10.dump()}"
    assert "30" in r10.text, (
        f"26.10: Expected '30' in cost summary text.\n{r10.dump()}"
    )

    # ── 26.11  Day summary ──
    r11 = await e2e.chat(msgs[10])
    assert r11.error is None, f"26.11 error: {r11.error}\n{r11.dump()}"
    text = r11.text
    # Summary should mention key events of the day
    has_food = "狗粮" in text or "喂" in text or "food" in text.lower()
    has_park = "公园" in text or "散步" in text or "park" in text.lower() or "walk" in text.lower()
    has_vomit = "吐" in text or "呕" in text or "vomit" in text.lower()
    assert has_food and has_park and has_vomit, (
        f"26.11: Summary should mention feeding, park walk, and vomiting. "
        f"food={has_food}, park={has_park}, vomit={has_vomit}.\n{r11.dump()}"
    )
