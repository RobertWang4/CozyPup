"""E2E test for §28: Pet onboarding full flow.

A single sequential test on a fresh user that creates a cat and walks through
the full pet profile setup: create → breed → gender/neuter → weight/birthday →
allergy → avatar → profile summary → query records.
"""

import pytest

from .conftest import E2EClient, get_tools_called, load_test_image
from .test_messages import MESSAGES


MSGS = MESSAGES["28_seq"]["zh"]


@pytest.mark.asyncio
async def test_28_pet_onboard_flow(e2e_debug):
    """§28: Full pet onboarding flow — 8 sequential steps (Chinese)."""
    e2e: E2EClient = e2e_debug

    # ── 28.1  Create cat ───────────────────────────────────────────────
    r = await e2e.chat(MSGS[0])  # "我养了一只新猫叫花花"
    assert r.error is None, f"28.1 chat error: {r.error}\n{r.dump()}"
    assert r.has_card("pet_created"), (
        f"28.1 Expected pet_created card.\n{r.dump()}"
    )
    card = r.first_card("pet_created")
    assert card.get("species") == "cat", (
        f"28.1 Expected species=cat, got {card.get('species')}.\n{r.dump()}"
    )

    # ── 28.2  Set breed ────────────────────────────────────────────────
    r = await e2e.chat(MSGS[1])  # "她是英短蓝猫"
    assert r.error is None, f"28.2 chat error: {r.error}\n{r.dump()}"
    pets = await e2e.get_pets()
    assert len(pets) >= 1, "28.2 No pets found."
    pet = [p for p in pets if p["name"] == "花花"][0]
    breed = (pet.get("breed") or "").lower()
    assert "英短" in (pet.get("breed") or "") or "british" in breed, (
        f"28.2 Expected breed to contain '英短' or 'British'. Got: {pet.get('breed')}"
    )

    # ── 28.3  Set gender + neutered ────────────────────────────────────
    r = await e2e.chat(MSGS[2])  # "母的，已经绝育了"
    assert r.error is None, f"28.3 chat error: {r.error}\n{r.dump()}"
    pets = await e2e.get_pets()
    pet = [p for p in pets if p["name"] == "花花"][0]
    gender = pet.get("gender") or pet.get("sex")
    assert gender is not None and gender != "", (
        f"28.3 Expected gender to be set. Pet: {pet}"
    )

    # ── 28.4  Set weight + birthday ────────────────────────────────────
    r = await e2e.chat(MSGS[3])  # "体重4公斤，生日2023年6月"
    assert r.error is None, f"28.4 chat error: {r.error}\n{r.dump()}"
    pets = await e2e.get_pets()
    pet = [p for p in pets if p["name"] == "花花"][0]
    weight = pet.get("weight") or pet.get("weight_kg")
    assert weight is not None, f"28.4 Weight not set. Pet: {pet}"
    assert abs(float(weight) - 4) < 1, (
        f"28.4 Expected weight ~4kg, got {weight}."
    )
    birthday = pet.get("birthday") or ""
    assert "2023" in birthday, (
        f"28.4 Expected birthday to contain '2023'. Got: {birthday}"
    )

    # ── 28.5  Set allergy note in profile ──────────────────────────────
    r = await e2e.chat(MSGS[4])  # "对鸡肉过敏"
    assert r.error is None, f"28.5 chat error: {r.error}\n{r.dump()}"
    pets = await e2e.get_pets()
    pet = [p for p in pets if p["name"] == "花花"][0]
    profile = (pet.get("profile_md") or pet.get("profile") or "")
    assert "过敏" in profile or "allergy" in profile.lower() or "鸡" in profile, (
        f"28.5 Expected profile to mention allergy. Profile: {profile}"
    )

    # ── 28.6  Set avatar via image ─────────────────────────────────────
    img_b64 = load_test_image()
    r = await e2e.chat(MSGS[5], images=[img_b64])  # "用这张当头像" + image
    assert r.error is None, f"28.6 chat error: {r.error}\n{r.dump()}"
    tools = get_tools_called(r)
    assert "set_pet_avatar" in tools, (
        f"28.6 Expected set_pet_avatar in tools_called={tools}.\n{r.dump()}"
    )
    pets = await e2e.get_pets()
    pet = [p for p in pets if p["name"] == "花花"][0]
    avatar_url = pet.get("avatar_url") or pet.get("avatar") or ""
    assert avatar_url, (
        f"28.6 Expected avatar_url to be non-empty. Pet: {pet}"
    )

    # ── 28.7  Summarize profile ────────────────────────────────────────
    r = await e2e.chat(MSGS[6])  # "帮我总结一下花花的档案"
    assert r.error is None, f"28.7 chat error: {r.error}\n{r.dump()}"
    tools = get_tools_called(r)
    assert "summarize_pet_profile" in tools, (
        f"28.7 Expected summarize_pet_profile in tools_called={tools}.\n{r.dump()}"
    )
    text = r.text
    # Should mention key profile facts
    assert any(kw in text for kw in ["英短", "British", "4", "过敏", "allergy"]), (
        f"28.7 Expected summary to mention breed/weight/allergy info. Text: {text}"
    )

    # ── 28.8  Query records → none yet ─────────────────────────────────
    r = await e2e.chat(MSGS[7])  # "花花有什么记录吗"
    assert r.error is None, f"28.8 chat error: {r.error}\n{r.dump()}"
    text = r.text
    # Should indicate no records exist (various phrasings)
    assert any(kw in text for kw in [
        "没有", "暂无", "还没", "无记录", "no record", "没有记录", "尚未",
    ]), (
        f"28.8 Expected reply to say no records. Text: {text}"
    )
