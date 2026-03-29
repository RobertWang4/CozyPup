"""E2E tests for calendar event tools (TEST_PLAN 2.1-2.7, 3.1-3.3, 4.1-4.4)."""

import pytest

from .conftest import E2EClient, has_cjk, today_str, yesterday_str
from .test_messages import MESSAGES


# ═══════════════════════════════════════════════════════════════════════════
# Section 2: Create calendar events
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_2_1_diet_event(e2e_with_pet: E2EClient, lang: str):
    """2.1 'ate dog food today' -> record card, category=diet, date=today."""
    e2e = e2e_with_pet
    result = await e2e.chat(MESSAGES["2.1"][lang])

    assert result.error is None, f"Chat error: {result.error}"
    assert result.has_card("record"), (
        f"Expected a record card.\n{result.dump()}"
    )

    card = result.first_card("record")
    assert card["category"] == "diet", (
        f"Expected category=diet, got {card.get('category')}.\n{result.dump()}"
    )
    assert card["date"] == today_str(), (
        f"Expected date={today_str()}, got {card.get('date')}.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_2_2_walk_yesterday(e2e_with_pet: E2EClient, lang: str):
    """2.2 'went to the park yesterday' -> record card, date=yesterday, category=daily."""
    e2e = e2e_with_pet
    result = await e2e.chat(MESSAGES["2.2"][lang])

    assert result.error is None, f"Chat error: {result.error}"
    assert result.has_card("record"), (
        f"Expected a record card.\n{result.dump()}"
    )

    card = result.first_card("record")
    assert card["date"] == yesterday_str(), (
        f"Expected date={yesterday_str()}, got {card.get('date')}.\n{result.dump()}"
    )
    assert card["category"] == "daily", (
        f"Expected category=daily, got {card.get('category')}.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_2_3_vaccine_last_friday(e2e_with_pet: E2EClient, lang: str):
    """2.3 'got vaccinated last Friday' -> record card, category=medical."""
    e2e = e2e_with_pet
    result = await e2e.chat(MESSAGES["2.3"][lang])

    assert result.error is None, f"Chat error: {result.error}"
    assert result.has_card("record"), (
        f"Expected a record card.\n{result.dump()}"
    )

    card = result.first_card("record")
    assert card["category"] == "medical", (
        f"Expected category=medical, got {card.get('category')}.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_2_4_ambiguous_date(e2e_with_pet: E2EClient, lang: str):
    """2.4 'took Weiwei to hospital last week' -> no event, should ask clarifying question."""
    e2e = e2e_with_pet
    result = await e2e.chat(MESSAGES["2.4"][lang])

    assert result.error is None, f"Chat error: {result.error}"
    assert not result.has_card("record"), (
        f"Should NOT create a record for ambiguous date.\n{result.dump()}"
    )
    # Should ask a clarifying question
    assert "?" in result.text or "\uff1f" in result.text, (
        f"Expected a clarifying question (contains ? or \uff1f).\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_2_5_specific_date(e2e_with_pet: E2EClient, lang: str):
    """2.5 'had a checkup on March 20th' -> record card, category=medical."""
    e2e = e2e_with_pet
    result = await e2e.chat(MESSAGES["2.5"][lang])

    assert result.error is None, f"Chat error: {result.error}"
    assert result.has_card("record"), (
        f"Expected a record card.\n{result.dump()}"
    )

    card = result.first_card("record")
    assert card["category"] == "medical", (
        f"Expected category=medical, got {card.get('category')}.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_2_6_abnormal(e2e_with_pet: E2EClient, lang: str):
    """2.6 'Weiwei vomited' -> record card, category=abnormal."""
    e2e = e2e_with_pet
    result = await e2e.chat(MESSAGES["2.6"][lang])

    assert result.error is None, f"Chat error: {result.error}"
    assert result.has_card("record"), (
        f"Expected a record card.\n{result.dump()}"
    )

    card = result.first_card("record")
    assert card["category"] == "abnormal", (
        f"Expected category=abnormal, got {card.get('category')}.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_2_7_multi_event(e2e_with_pet: E2EClient, lang: str):
    """2.7 'walked the dog and gave a bath today' -> 2 record cards."""
    e2e = e2e_with_pet
    result = await e2e.chat(MESSAGES["2.7"][lang])

    assert result.error is None, f"Chat error: {result.error}"
    assert result.card_count("record") >= 2, (
        f"Expected at least 2 record cards, got {result.card_count('record')}.\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Section 2.8-2.10: Category consolidation tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_2_8_diarrhea_is_abnormal(e2e_with_pet: E2EClient, lang: str):
    """2.8 'has diarrhea' -> record card, category=abnormal (was excretion)."""
    e2e = e2e_with_pet
    result = await e2e.chat(MESSAGES["2.8"][lang])

    assert result.error is None, f"Chat error: {result.error}"
    assert result.has_card("record"), (
        f"Expected a record card.\n{result.dump()}"
    )

    card = result.first_card("record")
    assert card["category"] == "abnormal", (
        f"Expected category=abnormal, got {card.get('category')}.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_2_9_deworming_is_medical(e2e_with_pet: E2EClient, lang: str):
    """2.9 'dewormed today' -> record card, category=medical (was deworming)."""
    e2e = e2e_with_pet
    result = await e2e.chat(MESSAGES["2.9"][lang])

    assert result.error is None, f"Chat error: {result.error}"
    assert result.has_card("record"), (
        f"Expected a record card.\n{result.dump()}"
    )

    card = result.first_card("record")
    assert card["category"] == "medical", (
        f"Expected category=medical, got {card.get('category')}.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_2_10_swimming_is_daily(e2e_with_pet: E2EClient, lang: str):
    """2.10 'went swimming' -> record card, category=daily."""
    e2e = e2e_with_pet
    result = await e2e.chat(MESSAGES["2.10"][lang])

    assert result.error is None, f"Chat error: {result.error}"
    assert result.has_card("record"), (
        f"Expected a record card.\n{result.dump()}"
    )

    card = result.first_card("record")
    assert card["category"] == "daily", (
        f"Expected category=daily, got {card.get('category')}.\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Section 3: Query events (setup + query)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_3_1_query_vaccine(e2e_with_pet: E2EClient, lang: str):
    """3.1 Create a vaccine event, then ask when the last vaccination was."""
    e2e = e2e_with_pet

    # Setup: create a vaccine event
    setup = await e2e.chat(MESSAGES["2.3"][lang])
    assert setup.error is None, f"Setup failed: {setup.error}"

    # Query
    result = await e2e.chat(MESSAGES["3.1"][lang])

    assert result.error is None, f"Chat error: {result.error}"
    assert result.text.strip(), f"Empty response.\n{result.dump()}"
    # Response should mention vaccination-related content
    text_lower = result.text.lower()
    has_vaccine_ref = any(
        kw in text_lower
        for kw in ["vaccin", "vaccine", "疫苗", "打针", "接种"]
    )
    assert has_vaccine_ref, (
        f"Expected response to mention vaccination.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_3_2_query_week(e2e_with_pet: E2EClient, lang: str):
    """3.2 Create some events, then ask 'what was recorded this week?'."""
    e2e = e2e_with_pet

    # Setup: create an event
    setup = await e2e.chat(MESSAGES["2.1"][lang])
    assert setup.error is None, f"Setup failed: {setup.error}"

    # Query
    result = await e2e.chat(MESSAGES["3.2"][lang])

    assert result.error is None, f"Chat error: {result.error}"
    assert result.text.strip(), f"Empty response.\n{result.dump()}"


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_3_3_query_diet(e2e_with_pet: E2EClient, lang: str):
    """3.3 Create a diet event, then ask 'what has Weiwei eaten recently?'."""
    e2e = e2e_with_pet

    # Setup: create a diet event
    setup = await e2e.chat(MESSAGES["2.1"][lang])
    assert setup.error is None, f"Setup failed: {setup.error}"

    # Query
    result = await e2e.chat(MESSAGES["3.3"][lang])

    assert result.error is None, f"Chat error: {result.error}"
    assert result.text.strip(), f"Empty response.\n{result.dump()}"
    # Response should reference food/diet
    text_lower = result.text.lower()
    has_diet_ref = any(
        kw in text_lower
        for kw in ["food", "ate", "eat", "diet", "狗粮", "吃", "饮食", "食"]
    )
    assert has_diet_ref, (
        f"Expected response to mention food/diet.\n{result.dump()}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Section 4: Update / Delete events
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_4_1_update_date(e2e_with_pet: E2EClient, lang: str):
    """4.1 Create an event, then correct its date to March 25th."""
    e2e = e2e_with_pet

    # Setup: create an event
    setup = await e2e.chat(MESSAGES["2.1"][lang])
    assert setup.error is None, f"Setup failed: {setup.error}"
    assert setup.has_card("record"), f"Setup: no record card.\n{setup.dump()}"

    # Update: correct the date
    result = await e2e.chat(MESSAGES["4.1"][lang])
    assert result.error is None, f"Chat error: {result.error}"

    # Verify via API that an event exists on March 25th
    events = await e2e.get_events(date_str="2026-03-25")
    assert len(events) > 0, (
        f"Expected event on 2026-03-25 after update, found none.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_4_2_delete_with_confirm(e2e_with_pet: E2EClient, lang: str):
    """4.2 Create a walk event, then ask to delete -> should get confirm_action card."""
    e2e = e2e_with_pet

    # Setup: create a walk event (yesterday)
    setup = await e2e.chat(MESSAGES["2.2"][lang])
    assert setup.error is None, f"Setup failed: {setup.error}"
    assert setup.has_card("record"), f"Setup: no record card.\n{setup.dump()}"

    # Delete request
    result = await e2e.chat(MESSAGES["4.2"][lang])
    assert result.error is None, f"Chat error: {result.error}"
    assert result.has_card("confirm_action"), (
        f"Expected a confirm_action card for delete.\n{result.dump()}"
    )

    confirm_card = result.first_card("confirm_action")
    assert "action_id" in confirm_card, (
        f"confirm_action card missing action_id.\n{result.dump()}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
async def test_4_3_confirm_delete(e2e_with_pet: E2EClient, lang: str):
    """4.3 Full delete flow: create -> request delete -> confirm -> verify deleted."""
    e2e = e2e_with_pet

    # Setup: create a walk event (yesterday)
    setup = await e2e.chat(MESSAGES["2.2"][lang])
    assert setup.error is None, f"Setup failed: {setup.error}"
    assert setup.has_card("record"), f"Setup: no record card.\n{setup.dump()}"

    # Verify event exists
    events_before = await e2e.get_events(date_str=yesterday_str())
    assert len(events_before) > 0, (
        f"Setup: expected event on {yesterday_str()}, found none."
    )

    # Delete request -> get confirm card
    delete_result = await e2e.chat(MESSAGES["4.2"][lang])
    assert delete_result.error is None, f"Delete request error: {delete_result.error}"
    assert delete_result.has_card("confirm_action"), (
        f"Expected confirm_action card.\n{delete_result.dump()}"
    )

    action_id = delete_result.first_card("confirm_action")["action_id"]

    # Confirm the deletion
    confirm_resp = await e2e.confirm_action(action_id)
    assert confirm_resp is not None, "confirm_action returned None"

    # Verify event is gone
    events_after = await e2e.get_events(date_str=yesterday_str())
    assert len(events_after) < len(events_before), (
        f"Expected fewer events after delete. Before: {len(events_before)}, "
        f"After: {len(events_after)}.\n{delete_result.dump()}"
    )
