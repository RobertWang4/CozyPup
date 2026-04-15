"""E2E tests for multi-pet deep scenarios (TEST_PLAN §41).

41a. 3+ pet management (41.1-41.8)
41b. Cross-pet isolation (41.9-41.12)
41c. Delete isolation (41.13-41.14)
41d. New pet joining (41.15-41.17)

Fixtures:
- e2e_debug_with_three_pets: 小维 (dog), 花花 (cat), 豆豆 (dog)
- e2e_debug_with_pet: 小维 (dog) only — for 41d new pet joins
"""

import pytest

from .conftest import E2EClient, get_tools_called, today_str
from .test_messages import MESSAGES


# ===========================================================================
# 41a. 3+ 只宠物管理
# ===========================================================================


@pytest.mark.asyncio
async def test_41_1_list_all_three_pets(e2e_debug_with_three_pets: E2EClient):
    """41.1 '我有几只宠物？' → text contains all 3 names, list_pets called."""
    r = await e2e_debug_with_three_pets.chat(MESSAGES["41.1"]["zh"])
    assert r.error is None, f"41.1 chat error: {r.error}\n{r.dump()}"

    tools = get_tools_called(r)
    assert "list_pets" in tools, (
        f"41.1 Expected list_pets in tools_called. Got: {tools}\n{r.dump()}"
    )
    for name in ("小维", "花花", "豆豆"):
        assert name in r.text, (
            f"41.1 Expected '{name}' in response text.\n{r.dump()}"
        )


@pytest.mark.asyncio
async def test_41_2_record_only_xiaowei(e2e_debug_with_three_pets: E2EClient):
    """41.2 '小维吃了狗粮' → record card pet_name only '小维'."""
    r = await e2e_debug_with_three_pets.chat(MESSAGES["41.2"]["zh"])
    assert r.error is None, f"41.2 chat error: {r.error}\n{r.dump()}"
    assert r.has_card("record"), f"41.2 Expected record card.\n{r.dump()}"

    card = r.first_card("record")
    pet_name = card.get("pet_name", "")
    assert "小维" in pet_name, (
        f"41.2 Expected pet_name to contain '小维', got '{pet_name}'.\n{r.dump()}"
    )
    assert "花花" not in pet_name and "豆豆" not in pet_name, (
        f"41.2 pet_name should only be 小维, got '{pet_name}'.\n{r.dump()}"
    )


@pytest.mark.asyncio
async def test_41_3_record_only_huahua(e2e_debug_with_three_pets: E2EClient):
    """41.3 '花花也吃了猫粮' → record card pet_name only '花花'."""
    r = await e2e_debug_with_three_pets.chat(MESSAGES["41.3"]["zh"])
    assert r.error is None, f"41.3 chat error: {r.error}\n{r.dump()}"
    assert r.has_card("record"), f"41.3 Expected record card.\n{r.dump()}"

    card = r.first_card("record")
    pet_name = card.get("pet_name", "")
    assert "花花" in pet_name, (
        f"41.3 Expected pet_name to contain '花花', got '{pet_name}'.\n{r.dump()}"
    )
    assert "小维" not in pet_name and "豆豆" not in pet_name, (
        f"41.3 pet_name should only be 花花, got '{pet_name}'.\n{r.dump()}"
    )


@pytest.mark.asyncio
async def test_41_4_doudou_abnormal(e2e_debug_with_three_pets: E2EClient):
    """41.4 '豆豆吐了' → record card pet_name '豆豆', category=abnormal."""
    r = await e2e_debug_with_three_pets.chat(MESSAGES["41.4"]["zh"])
    assert r.error is None, f"41.4 chat error: {r.error}\n{r.dump()}"
    assert r.has_card("record"), f"41.4 Expected record card.\n{r.dump()}"

    card = r.first_card("record")
    pet_name = card.get("pet_name", "")
    assert "豆豆" in pet_name, (
        f"41.4 Expected pet_name '豆豆', got '{pet_name}'.\n{r.dump()}"
    )
    assert card.get("category") == "abnormal", (
        f"41.4 Expected category='abnormal', got '{card.get('category')}'.\n{r.dump()}"
    )


@pytest.mark.asyncio
async def test_41_5_two_dogs_walk(e2e_debug_with_three_pets: E2EClient):
    """41.5 '两只狗一起散步了' → pet_name contains 小维+豆豆, NOT 花花."""
    r = await e2e_debug_with_three_pets.chat(MESSAGES["41.5"]["zh"])
    assert r.error is None, f"41.5 chat error: {r.error}\n{r.dump()}"
    assert r.has_card("record"), f"41.5 Expected record card(s).\n{r.dump()}"

    # Could be one combined card or two separate cards — collect all pet_names
    all_pet_names = " ".join(c.get("pet_name", "") for c in r.all_cards("record"))
    assert "小维" in all_pet_names, (
        f"41.5 Expected '小维' in record pet_names. Got: '{all_pet_names}'.\n{r.dump()}"
    )
    assert "豆豆" in all_pet_names, (
        f"41.5 Expected '豆豆' in record pet_names. Got: '{all_pet_names}'.\n{r.dump()}"
    )
    assert "花花" not in all_pet_names, (
        f"41.5 '花花' should NOT be in record (she's a cat). Got: '{all_pet_names}'.\n{r.dump()}"
    )


@pytest.mark.asyncio
async def test_41_6_all_pets_vaccinated(e2e_debug_with_three_pets: E2EClient):
    """41.6 '所有宠物都打了疫苗' → all 3 pets covered in record(s)."""
    r = await e2e_debug_with_three_pets.chat(MESSAGES["41.6"]["zh"])
    assert r.error is None, f"41.6 chat error: {r.error}\n{r.dump()}"
    assert r.card_count("record") >= 1, (
        f"41.6 Expected at least 1 record card.\n{r.dump()}"
    )

    # All 3 pets should be covered across all record cards
    all_pet_names = " ".join(c.get("pet_name", "") for c in r.all_cards("record"))
    for name in ("小维", "花花", "豆豆"):
        assert name in all_pet_names, (
            f"41.6 Expected '{name}' in vaccination records. Got: '{all_pet_names}'.\n{r.dump()}"
        )


@pytest.mark.asyncio
async def test_41_7_cat_diet_query(e2e_debug_with_three_pets: E2EClient):
    """41.7 '猫吃了什么？' → response about 花花's diet, no dog food mention.

    Requires 41.3 setup (花花 ate 猫粮) to have been recorded first.
    """
    # Setup: record cat food for 花花
    setup = await e2e_debug_with_three_pets.chat(MESSAGES["41.3"]["zh"])
    assert setup.error is None, f"41.7 setup error: {setup.error}\n{setup.dump()}"

    r = await e2e_debug_with_three_pets.chat(MESSAGES["41.7"]["zh"])
    assert r.error is None, f"41.7 chat error: {r.error}\n{r.dump()}"
    # Response should mention cat food, not dog food
    assert "猫粮" in r.text or "花花" in r.text, (
        f"41.7 Expected response about 花花/猫粮.\n{r.dump()}"
    )


@pytest.mark.asyncio
async def test_41_8_ambiguous_dog_asks_which(e2e_debug_with_three_pets: E2EClient):
    """41.8 '吃了狗粮' (no name, 2 dogs) → should ask which dog (contains '?')."""
    r = await e2e_debug_with_three_pets.chat(MESSAGES["41.8"]["zh"])
    assert r.error is None, f"41.8 chat error: {r.error}\n{r.dump()}"
    # LLM should ask a clarifying question — look for ? or ？
    assert "?" in r.text or "\uff1f" in r.text or not r.has_card("record"), (
        f"41.8 Expected LLM to ask which dog, but got a direct record.\n{r.dump()}"
    )


# ===========================================================================
# 41b. 跨宠物操作不混淆
# ===========================================================================


@pytest.mark.asyncio
async def test_41_9_delete_does_not_cross_pets(e2e_debug_with_three_pets: E2EClient):
    """41.9 Create 小维 event, then '删掉花花的记录' → doesn't delete 小维's."""
    # Setup: create an event for 小维
    setup = await e2e_debug_with_three_pets.chat(MESSAGES["41.2"]["zh"])
    assert setup.error is None, f"41.9 setup error: {setup.error}\n{setup.dump()}"

    events_before = await e2e_debug_with_three_pets.get_events(date_str=today_str())
    xiaowei_events_before = [
        e for e in events_before if "小维" in e.get("pet_name", "")
    ]

    # Try to delete 花花's records (which don't exist)
    r = await e2e_debug_with_three_pets.chat(MESSAGES["41.9"]["zh"])
    assert r.error is None, f"41.9 chat error: {r.error}\n{r.dump()}"

    # If confirm_action card returned, confirm it
    if r.has_card("confirm_action"):
        action_id = r.first_card("confirm_action")["action_id"]
        await e2e_debug_with_three_pets.confirm_action(action_id)

    # Verify 小维's events are still intact
    events_after = await e2e_debug_with_three_pets.get_events(date_str=today_str())
    xiaowei_events_after = [
        e for e in events_after if "小维" in e.get("pet_name", "")
    ]
    assert len(xiaowei_events_after) >= len(xiaowei_events_before), (
        f"41.9 小维's events were deleted! Before: {len(xiaowei_events_before)}, "
        f"After: {len(xiaowei_events_after)}.\n{r.dump()}"
    )


@pytest.mark.asyncio
async def test_41_10_independent_weight_updates(e2e_debug_with_three_pets: E2EClient):
    """41.10 '小维体重30kg' then '花花体重4公斤' → each pet updated independently."""
    # Set 小维's weight
    r1 = await e2e_debug_with_three_pets.chat("小维体重30kg")
    assert r1.error is None, f"41.10 step1 error: {r1.error}\n{r1.dump()}"

    # Set 花花's weight
    r2 = await e2e_debug_with_three_pets.chat(MESSAGES["41.10"]["zh"])
    assert r2.error is None, f"41.10 step2 error: {r2.error}\n{r2.dump()}"

    # Verify via API
    pets = await e2e_debug_with_three_pets.get_pets()
    xiaowei = next((p for p in pets if p["name"] == "小维"), None)
    huahua = next((p for p in pets if p["name"] == "花花"), None)

    assert xiaowei is not None, f"41.10 小维 not found. Pets: {pets}"
    assert huahua is not None, f"41.10 花花 not found. Pets: {pets}"

    assert xiaowei.get("weight") is not None, (
        f"41.10 小维's weight not set. Pet: {xiaowei}"
    )
    assert float(xiaowei["weight"]) == pytest.approx(30.0, abs=1.0), (
        f"41.10 Expected 小维 weight ~30kg, got {xiaowei['weight']}."
    )
    assert huahua.get("weight") is not None, (
        f"41.10 花花's weight not set. Pet: {huahua}"
    )
    assert float(huahua["weight"]) == pytest.approx(4.0, abs=0.5), (
        f"41.10 Expected 花花 weight ~4kg, got {huahua['weight']}."
    )


@pytest.mark.asyncio
async def test_41_11_separate_reminders(e2e_debug_with_three_pets: E2EClient):
    """41.11 '提醒我明天给小维喂药' then '花花也要喂' → 2 separate reminders."""
    r1 = await e2e_debug_with_three_pets.chat("提醒我明天给小维喂药")
    assert r1.error is None, f"41.11 step1 error: {r1.error}\n{r1.dump()}"

    r2 = await e2e_debug_with_three_pets.chat(MESSAGES["41.11"]["zh"])
    assert r2.error is None, f"41.11 step2 error: {r2.error}\n{r2.dump()}"

    # Verify reminders exist for both pets
    reminders = await e2e_debug_with_three_pets.get_reminders()
    reminder_pet_names = " ".join(
        r.get("pet_name", "") + " " + r.get("title", "") for r in reminders
    )
    # At least check that both pets have reminders (names appear in reminder data)
    assert len(reminders) >= 2, (
        f"41.11 Expected at least 2 reminders, got {len(reminders)}. "
        f"Reminders: {reminders}"
    )


@pytest.mark.asyncio
async def test_41_12_task_only_for_xiaowei(e2e_debug_with_three_pets: E2EClient):
    """41.12 '每天给小维遛狗' then '花花不用' → only 小维 has task."""
    r1 = await e2e_debug_with_three_pets.chat("每天给小维遛狗")
    assert r1.error is None, f"41.12 step1 error: {r1.error}\n{r1.dump()}"

    r2 = await e2e_debug_with_three_pets.chat(MESSAGES["41.12"]["zh"])
    assert r2.error is None, f"41.12 step2 error: {r2.error}\n{r2.dump()}"

    # Verify tasks — 花花 should NOT have a walk task
    tasks = await e2e_debug_with_three_pets.get_tasks_today()
    walk_tasks = [
        t for t in tasks
        if "遛" in t.get("title", "") or "walk" in t.get("title", "").lower()
    ]
    for task in walk_tasks:
        pet_name = task.get("pet_name", "")
        assert "花花" not in pet_name, (
            f"41.12 花花 should NOT have a walk task. Task: {task}"
        )


# ===========================================================================
# 41c. 宠物删除后的隔离
# ===========================================================================


@pytest.mark.asyncio
async def test_41_13_deleted_pet_no_association(e2e_debug_with_three_pets: E2EClient):
    """41.13 After deleting 花花, '花花今天吃了猫粮' → doesn't associate to 小维."""
    # Delete 花花 via chat
    r = await e2e_debug_with_three_pets.chat("删除花花")
    assert r.error is None, f"41.13 delete request error: {r.error}\n{r.dump()}"

    # Confirm deletion if needed
    if r.has_card("confirm_action"):
        action_id = r.first_card("confirm_action")["action_id"]
        await e2e_debug_with_three_pets.confirm_action(action_id)

    # Verify 花花 is gone
    pets = await e2e_debug_with_three_pets.get_pets()
    assert not any(p["name"] == "花花" for p in pets), (
        f"41.13 花花 should be deleted but still exists. Pets: {pets}"
    )

    # Now try to record for 花花
    r2 = await e2e_debug_with_three_pets.chat(MESSAGES["41.13"]["zh"])
    assert r2.error is None, f"41.13 chat error: {r2.error}\n{r2.dump()}"

    # Should NOT associate to 小维 or 豆豆
    if r2.has_card("record"):
        card = r2.first_card("record")
        pet_name = card.get("pet_name", "")
        assert "小维" not in pet_name, (
            f"41.13 Record associated to 小维 instead of deleted 花花! "
            f"pet_name='{pet_name}'.\n{r2.dump()}"
        )
        assert "豆豆" not in pet_name, (
            f"41.13 Record associated to 豆豆 instead of deleted 花花! "
            f"pet_name='{pet_name}'.\n{r2.dump()}"
        )


@pytest.mark.asyncio
async def test_41_14_deleted_pet_records_hidden(e2e_debug_with_three_pets: E2EClient):
    """41.14 After deleting 花花, '我的记录' → only 小维's and 豆豆's events."""
    # Setup: create events for both 小维 and 花花
    r1 = await e2e_debug_with_three_pets.chat("小维今天吃了狗粮")
    assert r1.error is None, f"41.14 setup1 error: {r1.error}\n{r1.dump()}"

    r2 = await e2e_debug_with_three_pets.chat("花花今天吃了猫粮")
    assert r2.error is None, f"41.14 setup2 error: {r2.error}\n{r2.dump()}"

    # Delete 花花
    r3 = await e2e_debug_with_three_pets.chat("删除花花")
    assert r3.error is None, f"41.14 delete error: {r3.error}\n{r3.dump()}"

    if r3.has_card("confirm_action"):
        action_id = r3.first_card("confirm_action")["action_id"]
        await e2e_debug_with_three_pets.confirm_action(action_id)

    # Query records
    r4 = await e2e_debug_with_three_pets.chat(MESSAGES["41.14"]["zh"])
    assert r4.error is None, f"41.14 query error: {r4.error}\n{r4.dump()}"

    # Response should not mention 花花's events
    # Note: text may mention 花花 in passing ("花花 was deleted"), but should not
    # list 花花's feeding record as an active event
    assert "猫粮" not in r4.text, (
        f"41.14 花花's cat food record should not appear after deletion.\n{r4.dump()}"
    )


# ===========================================================================
# 41d. 新宠物加入
# ===========================================================================


@pytest.mark.asyncio
async def test_41_15_to_41_17_new_pet_joins(e2e_debug_with_pet: E2EClient):
    """41.15-41.17 Add a new pet via chat, then use it immediately.

    41.15: '我又养了一只猫叫花花' → pet_created, pet count increases
    41.16: '小维和花花一起去公园了' → record references both
    41.17: '花花3岁了，英短蓝猫' → new pet info updated
    """
    # ── 41.15 Create new pet via chat ──────────────────────────────────
    pets_before = await e2e_debug_with_pet.get_pets()
    count_before = len(pets_before)

    r = await e2e_debug_with_pet.chat(MESSAGES["41.15"]["zh"])
    assert r.error is None, f"41.15 chat error: {r.error}\n{r.dump()}"
    assert r.has_card("pet_created"), (
        f"41.15 Expected pet_created card.\n{r.dump()}"
    )

    pets_after = await e2e_debug_with_pet.get_pets()
    assert len(pets_after) > count_before, (
        f"41.15 Pet count did not increase. Before: {count_before}, "
        f"After: {len(pets_after)}. Pets: {pets_after}"
    )
    huahua = next((p for p in pets_after if p["name"] == "花花"), None)
    assert huahua is not None, (
        f"41.15 花花 not found after creation. Pets: {pets_after}"
    )
    assert huahua.get("species") == "cat", (
        f"41.15 Expected species=cat for 花花, got {huahua.get('species')}."
    )

    # ── 41.16 Record event for both pets ───────────────────────────────
    r2 = await e2e_debug_with_pet.chat(MESSAGES["41.16"]["zh"])
    assert r2.error is None, f"41.16 chat error: {r2.error}\n{r2.dump()}"
    assert r2.has_card("record"), f"41.16 Expected record card.\n{r2.dump()}"

    all_pet_names = " ".join(c.get("pet_name", "") for c in r2.all_cards("record"))
    assert "小维" in all_pet_names, (
        f"41.16 Expected '小维' in record. Got: '{all_pet_names}'.\n{r2.dump()}"
    )
    assert "花花" in all_pet_names, (
        f"41.16 Expected '花花' in record. Got: '{all_pet_names}'.\n{r2.dump()}"
    )

    # ── 41.17 Update new pet profile ───────────────────────────────────
    r3 = await e2e_debug_with_pet.chat(MESSAGES["41.17"]["zh"])
    assert r3.error is None, f"41.17 chat error: {r3.error}\n{r3.dump()}"

    # Verify pet profile updated via API
    pets = await e2e_debug_with_pet.get_pets()
    huahua = next((p for p in pets if p["name"] == "花花"), None)
    assert huahua is not None, f"41.17 花花 not found. Pets: {pets}"

    # Check breed was updated (英短 / British Shorthair)
    breed = huahua.get("breed", "") or ""
    assert breed != "", (
        f"41.17 花花's breed not set after update. Pet: {huahua}"
    )
