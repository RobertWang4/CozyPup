"""Unit tests for app.agents.emergency_router.classify_emergency.

Coverage goal: for clear-cut emergencies the classifier fires (with the right
category); for non-emergency daily questions it stays silent. False positives
in the chat pipeline waste user trust; false negatives are the real danger.
"""

import pytest

from app.agents.emergency_router import classify_emergency, render_for_user


# --- Should match (positive cases) ---------------------------------------
POSITIVE_CASES = [
    ("我家狗吃了巧克力怎么办", "toxin_ingestion"),
    ("My dog ate a grape 10 minutes ago", "toxin_ingestion"),
    ("猫舔了百合花粉", "toxin_ingestion"),
    ("my dog swallowed ibuprofen", "toxin_ingestion"),
    ("狗狗突然抽搐", "seizure"),
    ("my cat is seizing right now", "seizure"),
    ("公猫一直蹲厕所尿不出来", "urinary_obstruction"),
    ("male cat can't pee, just straining", "urinary_obstruction"),
    ("my cat is open mouth breathing", "respiratory_distress"),
    ("狗狗牙龈发紫了", "respiratory_distress"),
    ("我家大狗肚子鼓胀得厉害还一直干呕吐不出", "gdv_bloat"),
    ("he's been trying to vomit nothing comes up and his belly is swollen", "gdv_bloat"),
    ("把狗留车里了现在中暑了", "heatstroke"),
    ("I think my dog has heatstroke", "heatstroke"),
    ("狗狗被车撞了流血不止", "severe_trauma"),
    ("my puppy was hit by a car", "severe_trauma"),
    ("母狗强烈宫缩30分钟还没生出小狗", "dystocia"),
    ("猫咪突然昏迷不动了", "collapse"),
    ("dog collapsed and won't wake up", "collapse"),
    ("狗吃了老鼠药", "toxin_ingestion"),
    ("my dog drank antifreeze from the garage", "toxin_ingestion"),
    ("狗舔了防冻液", "toxin_ingestion"),
    ("possible ethylene glycol exposure", "toxin_ingestion"),
    ("公狗尿不出来怎么办", "urinary_obstruction"),
    ("my male dog can't pee", "urinary_obstruction"),
]


# --- Should NOT match (non-emergencies) ----------------------------------
NEGATIVE_CASES = [
    "狗狗疫苗什么时候打",
    "my puppy's first vet visit",
    "猫驱虫多久一次",
    "how do I brush my dog's teeth",
    "小猫刚接回家怎么照顾",
    "狗耳朵有点痒",
    "cat has bad breath",
    "what food should I feed my 3 month old kitten",
    "今天天气怎么样",
    "tell me a joke",
    # Boundary: mentions "vomit" but not the unproductive-retching GDV signal
    "my dog threw up once this morning",
    "狗狗今天吐了一次",
]


@pytest.mark.parametrize("message,expected_category", POSITIVE_CASES)
def test_classifies_emergencies(message: str, expected_category: str) -> None:
    match = classify_emergency(message)
    assert match is not None, f"expected {expected_category}, got None for {message!r}"
    assert match.category == expected_category, (
        f"expected {expected_category}, got {match.category} for {message!r}"
    )
    assert match.hotline  # non-empty
    assert match.message_en and match.message_zh


@pytest.mark.parametrize("message", NEGATIVE_CASES)
def test_non_emergencies_return_none(message: str) -> None:
    assert classify_emergency(message) is None, f"unexpected match for {message!r}"


def test_render_for_user_shape() -> None:
    match = classify_emergency("我家狗吃了巧克力")
    assert match is not None
    payload = render_for_user(match, lang="zh")
    assert payload["type"] == "emergency"
    assert payload["category"] == "toxin_ingestion"
    assert payload["hotline"]
    assert payload["message"]  # Chinese message present
    assert payload["article_slug"] == "food_toxins"

    payload_en = render_for_user(match, lang="en")
    assert payload_en["message"] != payload["message"]  # language switched


def test_empty_input_returns_none() -> None:
    assert classify_emergency("") is None
    assert classify_emergency("   ") is None
