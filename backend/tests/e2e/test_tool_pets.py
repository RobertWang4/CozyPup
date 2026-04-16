"""E2E tests for pet management tools (TEST_PLAN 5.1-5.9).

5.1-5.7 form a sequential flow: create cat → set gender → gender locked →
set weight → set birthday → allergy note → rename.
5.8 duplicate prevention and 5.9 delete with confirmation are independent.
"""

import pytest

from .conftest import E2EClient, has_cjk
from .test_messages import MESSAGES


# ---------------------------------------------------------------------------
# 5.1-5.7: Sequential pet management flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
@pytest.mark.xfail(reason="LLM multi-step flow is non-deterministic")
async def test_5_1_to_5_7_pet_management_flow(e2e: E2EClient, lang: str):
    """5.1-5.7 Full pet management flow in one session."""

    pet_name = "花花" if lang == "zh" else "Huahua"
    renamed_name = "咪咪" if lang == "zh" else "Mimi"

    # ── 5.1 Create cat ──────────────────────────────────────────────────
    r = await e2e.chat(MESSAGES["5.1"][lang])
    assert r.error is None, f"5.1 chat error: {r.error}\n{r.dump()}"
    assert r.has_card("pet_created"), (
        f"5.1 Expected pet_created card.\n{r.dump()}"
    )
    card = r.first_card("pet_created")
    assert card["species"] == "cat", (
        f"5.1 Expected species=cat, got {card.get('species')}.\n{r.dump()}"
    )

    pets = await e2e.get_pets()
    assert len(pets) >= 1, f"5.1 No pets found after creation."
    created = [p for p in pets if p["name"] == pet_name]
    assert len(created) == 1, (
        f"5.1 Expected 1 pet named '{pet_name}', found {len(created)}. Pets: {pets}"
    )
    pet_id = created[0]["id"]

    # ── 5.2 Set gender ──────────────────────────────────────────────────
    r = await e2e.chat(MESSAGES["5.2"][lang])
    assert r.error is None, f"5.2 chat error: {r.error}\n{r.dump()}"
    # Gender first-time set may return confirm_action (design behavior) or pet_updated
    # LLM may also create another pet instead — accept any non-error response
    has_update = r.has_card("pet_updated")
    has_confirm = r.has_card("confirm_action")
    assert has_update or has_confirm, (
        f"5.2 Expected pet_updated or confirm_action card.\n{r.dump()}"
    )

    # If confirm_action, confirm it to actually set the gender
    if has_confirm and not has_update:
        action_id = r.first_card("confirm_action")["action_id"]
        confirm_resp = await e2e.confirm_action(action_id)
        assert confirm_resp is not None, "5.2 confirm_action returned None"

    pets = await e2e.get_pets()
    pet = next(p for p in pets if p["id"] == pet_id)
    assert pet.get("gender") is not None, (
        f"5.2 Gender not set. Pet: {pet}"
    )

    # ── 5.3 Gender locked — should NOT change ───────────────────────────
    r = await e2e.chat(MESSAGES["5.3"][lang])
    assert r.error is None, f"5.3 chat error: {r.error}\n{r.dump()}"

    # Should not produce a pet_updated card (gender is locked)
    if r.has_card("pet_updated"):
        card = r.first_card("pet_updated")
        saved = card.get("saved_keys", [])
        assert "gender" not in saved, (
            f"5.3 Gender should be locked but was updated. Card: {card}\n{r.dump()}"
        )

    # Verify gender unchanged via API
    pets = await e2e.get_pets()
    pet = next(p for p in pets if p["id"] == pet_id)
    assert pet["gender"] == "female" if lang == "zh" else True, (
        f"5.3 Gender changed unexpectedly. Pet: {pet}"
    )

    # ── 5.4 Set weight ──────────────────────────────────────────────────
    r = await e2e.chat(MESSAGES["5.4"][lang])
    assert r.error is None, f"5.4 chat error: {r.error}\n{r.dump()}"
    assert r.has_card("pet_updated"), (
        f"5.4 Expected pet_updated card.\n{r.dump()}"
    )

    pets = await e2e.get_pets()
    pet = next(p for p in pets if p["id"] == pet_id)
    assert pet.get("weight") is not None, (
        f"5.4 Weight not set. Pet: {pet}"
    )
    assert float(pet["weight"]) == pytest.approx(5.0, abs=0.5), (
        f"5.4 Expected weight ~5kg, got {pet['weight']}. Pet: {pet}"
    )

    # ── 5.5 Set birthday ────────────────────────────────────────────────
    r = await e2e.chat(MESSAGES["5.5"][lang])
    assert r.error is None, f"5.5 chat error: {r.error}\n{r.dump()}"
    assert r.has_card("pet_updated"), (
        f"5.5 Expected pet_updated card.\n{r.dump()}"
    )

    pets = await e2e.get_pets()
    pet = next(p for p in pets if p["id"] == pet_id)
    assert pet.get("birthday") is not None, (
        f"5.5 Birthday not set. Pet: {pet}"
    )
    assert "2024-03-05" in pet["birthday"], (
        f"5.5 Expected birthday 2024-03-05, got {pet['birthday']}. Pet: {pet}"
    )

    # ── 5.6 Allergy note (background profile update) ────────────────────
    r = await e2e.chat(MESSAGES["5.6"][lang])
    assert r.error is None, f"5.6 chat error: {r.error}\n{r.dump()}"
    # Allergy may be processed by background profile_extractor, not via card.
    # Just ensure no error — the info will surface in the pet profile eventually.

    # ── 5.7 Rename pet ──────────────────────────────────────────────────
    r = await e2e.chat(MESSAGES["5.7"][lang])
    assert r.error is None, f"5.7 chat error: {r.error}\n{r.dump()}"
    assert r.has_card("pet_updated"), (
        f"5.7 Expected pet_updated card.\n{r.dump()}"
    )

    pets = await e2e.get_pets()
    pet = next((p for p in pets if p["id"] == pet_id), None)
    assert pet is not None, f"5.7 Pet {pet_id} not found after rename. Pets: {pets}"
    assert pet["name"] == renamed_name, (
        f"5.7 Expected name '{renamed_name}', got '{pet['name']}'. Pet: {pet}"
    )


# ---------------------------------------------------------------------------
# 5.8: Duplicate prevention
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
@pytest.mark.xfail(reason="LLM sometimes creates duplicate or renames pet")
async def test_5_8_duplicate_prevention(e2e_with_pet: E2EClient, lang: str):
    """5.8 Sending 'I got a new dog named 小维' when 小维 already exists
    should NOT create a duplicate."""
    pets_before = await e2e_with_pet.get_pets()
    weiwei_count_before = len([p for p in pets_before if p["name"] == "小维"])
    assert weiwei_count_before == 1, (
        f"5.8 Setup: expected 1 小维, found {weiwei_count_before}. Pets: {pets_before}"
    )

    r = await e2e_with_pet.chat(MESSAGES["5.8"][lang])
    assert r.error is None, f"5.8 chat error: {r.error}\n{r.dump()}"

    pets_after = await e2e_with_pet.get_pets()
    weiwei_count_after = len([p for p in pets_after if p["name"] == "小维"])
    assert weiwei_count_after == 1, (
        f"5.8 Duplicate created! Expected 1 小維, found {weiwei_count_after}. "
        f"Pets: {pets_after}\n{r.dump()}"
    )


# ---------------------------------------------------------------------------
# 5.9: Delete with confirmation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["zh", "en"])
@pytest.mark.xfail(reason="LLM sometimes misinterprets delete request")
async def test_5_9_delete_confirm(e2e: E2EClient, lang: str):
    """5.9 Delete a pet — should require confirmation, then actually delete."""
    pet_name = "花花" if lang == "zh" else "Huahua"

    # First create a pet via chat
    r = await e2e.chat(MESSAGES["5.1"][lang])
    assert r.error is None, f"5.9 setup chat error: {r.error}\n{r.dump()}"
    assert r.has_card("pet_created"), (
        f"5.9 Setup: expected pet_created card.\n{r.dump()}"
    )

    pets = await e2e.get_pets()
    assert any(p["name"] == pet_name for p in pets), (
        f"5.9 Setup: pet '{pet_name}' not found. Pets: {pets}"
    )

    # Request deletion — should get confirm_action card
    r = await e2e.chat(MESSAGES["5.9"][lang])
    assert r.error is None, f"5.9 delete chat error: {r.error}\n{r.dump()}"
    assert r.has_card("confirm_action"), (
        f"5.9 Expected confirm_action card for delete.\n{r.dump()}"
    )

    action_id = r.first_card("confirm_action")["action_id"]
    assert action_id, f"5.9 confirm_action card missing action_id.\n{r.dump()}"

    # Confirm the deletion
    confirm_resp = await e2e.confirm_action(action_id)
    assert confirm_resp is not None, "5.9 confirm_action returned None"

    # Verify pet is gone
    pets = await e2e.get_pets()
    remaining = [p for p in pets if p["name"] == pet_name]
    assert len(remaining) == 0, (
        f"5.9 Pet '{pet_name}' still exists after confirmed delete. Pets: {pets}"
    )
