"""E2E test for §25: New user cold start flow.

A single sequential test that walks a brand-new user (no pets) through
8 messages: greeting → create pet → update details → record event →
correct date → set reminder → query records → update profile.
"""

import pytest

from .conftest import E2EClient, get_tools_called, load_test_image, yesterday_str
from .test_messages import MESSAGES


MSGS = MESSAGES["25_seq"]["en"]


@pytest.mark.asyncio
async def test_25_coldstart_flow(e2e_debug):
    """§25: Full cold-start onboarding flow — 8 sequential steps."""
    e2e: E2EClient = e2e_debug

    # ── 25.1  Greeting → product introduction ──────────────────────────
    r = await e2e.chat(MSGS[0])  # "Hello!"
    assert r.error is None, f"25.1 chat error: {r.error}\n{r.dump()}"
    assert r.text.strip(), f"25.1 Expected non-empty reply.\n{r.dump()}"
    tools = get_tools_called(r)
    assert "introduce_product" in tools, (
        f"25.1 Expected introduce_product in tools_called={tools}.\n{r.dump()}"
    )

    # ── 25.2  Create pet ───────────────────────────────────────────────
    r = await e2e.chat(MSGS[1])  # "I have a golden retriever named Winnie"
    assert r.error is None, f"25.2 chat error: {r.error}\n{r.dump()}"
    assert r.has_card("pet_created"), (
        f"25.2 Expected pet_created card.\n{r.dump()}"
    )
    card = r.first_card("pet_created")
    assert card.get("species") == "dog", (
        f"25.2 Expected species=dog, got {card.get('species')}.\n{r.dump()}"
    )

    # ── 25.3  Update age + weight ──────────────────────────────────────
    r = await e2e.chat(MSGS[2])  # "She's 3 years old, weighs 30kg"
    assert r.error is None, f"25.3 chat error: {r.error}\n{r.dump()}"
    pets = await e2e.get_pets()
    assert len(pets) >= 1, "25.3 No pets found."
    pet = pets[0]
    weight = pet.get("weight") or pet.get("weight_kg")
    assert weight is not None, f"25.3 Weight not set. Pet: {pet}"
    assert abs(float(weight) - 30) < 2, (
        f"25.3 Expected weight ~30kg, got {weight}. Pet: {pet}"
    )

    # ── 25.4  Record feeding event ─────────────────────────────────────
    r = await e2e.chat(MSGS[3])  # "She ate chicken and rice today"
    assert r.error is None, f"25.4 chat error: {r.error}\n{r.dump()}"
    assert r.has_card("record"), (
        f"25.4 Expected record card.\n{r.dump()}"
    )
    record_card = r.first_card("record")
    pet_name_in_card = (
        record_card.get("pet_name", "")
        or record_card.get("petName", "")
        or ""
    )
    assert "winnie" in pet_name_in_card.lower() or "Winnie" in str(record_card), (
        f"25.4 Expected pet_name to contain 'Winnie'. Card: {record_card}"
    )

    # ── 25.5  Correct date to yesterday ────────────────────────────────
    r = await e2e.chat(MSGS[4])  # "Actually that was yesterday"
    assert r.error is None, f"25.5 chat error: {r.error}\n{r.dump()}"
    tools = get_tools_called(r)
    assert "update_calendar_event" in tools, (
        f"25.5 Expected update_calendar_event in tools_called={tools}.\n{r.dump()}"
    )

    # ── 25.6  Create reminder ──────────────────────────────────────────
    r = await e2e.chat(MSGS[5])  # "Remind me to take her to the vet next Monday"
    assert r.error is None, f"25.6 chat error: {r.error}\n{r.dump()}"
    # Reminders are now merged into calendar events (record cards with reminder_at)
    assert r.has_card("record") or "remind" in r.text.lower() or "提醒" in r.text, (
        f"25.6 Expected record card or reminder mention.\n{r.dump()}"
    )

    # ── 25.7  Query records → mentions chicken/rice ────────────────────
    r = await e2e.chat(MSGS[6])  # "What have I recorded so far?"
    assert r.error is None, f"25.7 chat error: {r.error}\n{r.dump()}"
    text_lower = r.text.lower()
    assert "chicken" in text_lower or "rice" in text_lower, (
        f"25.7 Expected reply to mention 'chicken' or 'rice'. Text: {r.text}"
    )

    # ── 25.8  Update profile notes ─────────────────────────────────────
    r = await e2e.chat(MSGS[7])  # "She's scared of thunder and very shy"
    assert r.error is None, f"25.8 chat error: {r.error}\n{r.dump()}"
    pets = await e2e.get_pets()
    assert len(pets) >= 1, "25.8 No pets found."
    pet = pets[0]
    profile = (pet.get("profile_md") or pet.get("profile") or "").lower()
    assert "thunder" in profile or "shy" in profile, (
        f"25.8 Expected profile to mention 'thunder' or 'shy'. "
        f"Profile: {pet.get('profile_md') or pet.get('profile')}"
    )
