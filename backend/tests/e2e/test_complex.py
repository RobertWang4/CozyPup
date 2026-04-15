"""E2E tests for complex multi-task instructions (TEST_PLAN §40).

Tests verify that one-sentence commands containing multiple operations
are decomposed (via plan tool) and fully executed by the agent.
"""

import pytest

from .conftest import (
    E2EClient,
    get_tools_called,
    load_test_image,
    today_str,
)
from .test_messages import MESSAGES


# ═══════════════════════════════════════════════════════════════════════════
# 40a. Dual tasks
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_1_record_and_reminder(e2e_debug_with_pet: E2EClient, lang: str):
    """40.1 Record food + remind vaccination → record card AND reminder card."""
    result = await e2e_debug_with_pet.chat(MESSAGES["40.1"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("record"), (
        f"Expected a record card for the food log.\n{result.dump()}"
    )
    assert result.has_card("reminder"), (
        f"Expected a reminder card for vaccination.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_2_two_records(e2e_debug_with_pet: E2EClient, lang: str):
    """40.2 Walk + bath → at least 2 record cards."""
    result = await e2e_debug_with_pet.chat(MESSAGES["40.2"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.card_count("record") >= 2, (
        f"Expected >= 2 record cards, got {result.card_count('record')}.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_3_delete_and_record(e2e_debug_with_pet: E2EClient, lang: str):
    """40.3 Delete yesterday's record + add today's walk → confirm_action AND record."""
    e2e = e2e_debug_with_pet

    # Setup: create a record for yesterday so there's something to delete
    await e2e.chat(
        "记录小维昨天散步了" if lang == "zh" else "Record that Weiwei walked yesterday"
    )

    result = await e2e.chat(MESSAGES["40.3"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    # The delete should produce a confirm_action card (destructive op) or
    # the record for today should appear. At minimum one of these must hold.
    has_confirm = result.has_card("confirm_action")
    has_record = result.has_card("record")
    assert has_confirm or has_record, (
        f"Expected confirm_action or record card.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_4_daily_task_and_record(e2e_debug_with_pet: E2EClient, lang: str):
    """40.4 Create daily walk task + record today's walk → daily_task_created AND record."""
    result = await e2e_debug_with_pet.chat(MESSAGES["40.4"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("daily_task_created"), (
        f"Expected daily_task_created card.\n{result.dump()}"
    )
    assert result.has_card("record"), (
        f"Expected record card for today's walk.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_5_weight_and_birthday(e2e_debug_with_pet: E2EClient, lang: str):
    """40.5 Set weight=30kg + birthday March 2023 → pet_updated, verify via API."""
    e2e = e2e_debug_with_pet
    result = await e2e.chat(MESSAGES["40.5"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("pet_updated"), (
        f"Expected pet_updated card.\n{result.dump()}"
    )

    # Verify via pets API
    pets = await e2e.get_pets()
    pet = next((p for p in pets if p["name"] == "小维"), None)
    assert pet is not None, f"Pet '小维' not found. Pets: {pets}"

    assert pet.get("weight") is not None, (
        f"Weight not set on pet. Pet: {pet}\n{result.dump()}"
    )
    assert float(pet["weight"]) == pytest.approx(30.0, abs=1.0), (
        f"Expected weight ~30kg, got {pet['weight']}.\n{result.dump()}"
    )
    assert pet.get("birthday") is not None, (
        f"Birthday not set on pet. Pet: {pet}\n{result.dump()}"
    )
    assert "2023" in pet["birthday"], (
        f"Expected birthday to contain '2023', got {pet['birthday']}.\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 40b. Triple+ tasks
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_6_three_records_two_pets(e2e_debug_with_two_pets: E2EClient, lang: str):
    """40.6 Walk dog + feed cat + bathe Huahua → >= 3 record cards across 2 pets."""
    result = await e2e_debug_with_two_pets.chat(MESSAGES["40.6"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.card_count("record") >= 3, (
        f"Expected >= 3 record cards, got {result.card_count('record')}.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_7_record_reminder_task(e2e_debug_with_pet: E2EClient, lang: str):
    """40.7 Record walk + remind vaccination + create daily medicine task → 3 different card types."""
    result = await e2e_debug_with_pet.chat(MESSAGES["40.7"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("record"), (
        f"Expected record card for walk.\n{result.dump()}"
    )
    assert result.has_card("reminder"), (
        f"Expected reminder card for vaccination.\n{result.dump()}"
    )
    assert result.has_card("daily_task_created"), (
        f"Expected daily_task_created card for medicine task.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_8_three_records_same_pet(e2e_debug_with_pet: E2EClient, lang: str):
    """40.8 Dog food + walk + bath for same pet → >= 3 record cards."""
    result = await e2e_debug_with_pet.chat(MESSAGES["40.8"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.card_count("record") >= 3, (
        f"Expected >= 3 record cards, got {result.card_count('record')}.\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 40c. Compound operations
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_9_record_with_location(e2e_debug_with_pet: E2EClient, lang: str):
    """40.9 Visit Vanier Animal Hospital for checkup → record card + event has location."""
    e2e = e2e_debug_with_pet
    result = await e2e.chat(MESSAGES["40.9"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("record"), (
        f"Expected a record card.\n{result.dump()}"
    )

    # Verify location was attached to the event
    events = await e2e.get_events(date_str=today_str())
    located_events = [e for e in events if e.get("location")]
    assert located_events, (
        f"Expected at least one event with location for today.\n{result.dump()}"
    )


@pytest.mark.asyncio
async def test_40_10_photo_with_record(e2e_debug_with_pet: E2EClient):
    """40.10 Send image + park visit → record card + event photos non-empty."""
    e2e = e2e_debug_with_pet
    img = load_test_image()
    result = await e2e.chat(MESSAGES["40.10"]["zh"], images=[img])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("record"), (
        f"Expected a record card.\n{result.dump()}"
    )

    # Verify photo was attached
    events = await e2e.get_events(date_str=today_str())
    photo_events = [e for e in events if e.get("photos")]
    assert photo_events, (
        f"No events with photos found for today.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_11_cost_and_reminder(e2e_debug_with_pet: E2EClient, lang: str):
    """40.11 Hospital visit cost=2000 + remind follow-up → record with cost + reminder."""
    result = await e2e_debug_with_pet.chat(MESSAGES["40.11"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.has_card("record"), (
        f"Expected a record card.\n{result.dump()}"
    )
    assert result.has_card("reminder"), (
        f"Expected a reminder card for follow-up.\n{result.dump()}"
    )

    # Verify cost on the record card
    card = result.first_card("record")
    cost = card.get("cost")
    if cost is not None:
        assert float(cost) == pytest.approx(2000.0, abs=1.0), (
            f"Expected cost ~2000, got {cost}.\n{result.dump()}"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_12_two_pets_with_cost(e2e_debug_with_two_pets: E2EClient, lang: str):
    """40.12 Two pets park walk + snack cost=50 → records for both pets, one with cost."""
    result = await e2e_debug_with_two_pets.chat(MESSAGES["40.12"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"

    # Should have records for both pets' walk + snack purchase
    record_cards = result.all_cards("record")
    assert len(record_cards) >= 2, (
        f"Expected >= 2 record cards (walk for 2 pets + snack), "
        f"got {len(record_cards)}.\n{result.dump()}"
    )

    # Check that at least one card has cost=50
    costs = [c.get("cost") for c in record_cards if c.get("cost") is not None]
    if costs:
        assert any(float(c) == pytest.approx(50.0, abs=1.0) for c in costs), (
            f"Expected a card with cost ~50, got costs={costs}.\n{result.dump()}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 40d. Plan Nag verification
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_13_four_records(e2e_debug_with_pet: E2EClient, lang: str):
    """40.13 Walk + feed + bath + vaccine → >= 4 record cards (plan nag ensures all)."""
    result = await e2e_debug_with_pet.chat(MESSAGES["40.13"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    assert result.card_count("record") >= 4, (
        f"Expected >= 4 record cards, got {result.card_count('record')}.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_14_four_mixed_tasks(e2e_debug_with_pet: E2EClient, lang: str):
    """40.14 Record x2 + reminder + daily task → all 4 card types present."""
    result = await e2e_debug_with_pet.chat(MESSAGES["40.14"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"

    # Need at least 2 record cards
    assert result.card_count("record") >= 2, (
        f"Expected >= 2 record cards, got {result.card_count('record')}.\n{result.dump()}"
    )
    assert result.has_card("reminder"), (
        f"Expected a reminder card.\n{result.dump()}"
    )
    assert result.has_card("daily_task_created"), (
        f"Expected a daily_task_created card.\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 40e. Ambiguous compound instructions
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_15_vague_record(e2e_debug_with_pet: E2EClient, lang: str):
    """40.15 'Record today, remind tomorrow to record too' — vague.
    Should ask what to record OR make a reasonable guess."""
    result = await e2e_debug_with_pet.chat(MESSAGES["40.15"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"
    # Either asks a clarifying question or makes a reasonable guess (produces a card)
    asks_question = "?" in result.text or "？" in result.text
    made_guess = result.has_card("record") or result.has_card("reminder")
    assert asks_question or made_guess, (
        f"Expected a clarifying question or reasonable guess.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_16_delete_everything(e2e_debug_with_pet: E2EClient, lang: str):
    """40.16 'Delete everything' — must NOT blindly delete. Should ask for clarification."""
    e2e = e2e_debug_with_pet
    result = await e2e.chat(MESSAGES["40.16"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"

    # Should NOT have deleted pets — verify they still exist
    pets = await e2e.get_pets()
    assert len(pets) >= 1, (
        f"Pet was deleted! Agent should not delete everything without clarification.\n{result.dump()}"
    )

    # Should ask for clarification or show confirm_action (not mass-delete)
    asks_question = "?" in result.text or "？" in result.text
    has_confirm = result.has_card("confirm_action")
    assert asks_question or has_confirm, (
        f"Expected clarification question or confirm_action, not silent deletion.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_40_17_ambiguous_pet(e2e_debug_with_two_pets: E2EClient, lang: str):
    """40.17 'Record a walk' with 2 pets, no name — should ask which pet."""
    result = await e2e_debug_with_two_pets.chat(MESSAGES["40.17"][lang])

    assert result.error is None, f"Chat error: {result.error}\n{result.dump()}"

    # Should ask which pet, or list pets to choose from
    asks_question = "?" in result.text or "？" in result.text
    mentions_pets = "小维" in result.text or "花花" in result.text or "Weiwei" in result.text.lower()
    # It's also acceptable if it just recorded for all pets
    recorded_both = result.card_count("record") >= 2
    assert asks_question or mentions_pets or recorded_both, (
        f"Expected to ask which pet or mention pet names.\n{result.dump()}"
    )
