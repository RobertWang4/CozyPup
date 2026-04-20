"""Tests for rule-based intent detection."""

from app.rag.intent_filter import detect_intent


def test_plain_query_has_no_intent():
    assert detect_intent("狗呕吐") is None
    assert detect_intent("dog vaccine schedule") is None
    assert detect_intent("") is None


def test_toxic_food_ingestion_zh():
    hint = detect_intent("狗吃了巧克力")
    assert hint is not None
    assert hint.label == "toxin_food"
    assert any("toxic foods" in p.lower() for p in hint.boost_title_patterns)


def test_toxic_food_ingestion_en():
    hint = detect_intent("my dog ate grapes")
    assert hint is not None
    assert hint.label == "toxin_food"


def test_toxic_plant_ingestion_cat_lily():
    hint = detect_intent("猫吃了百合花")
    assert hint is not None
    assert hint.label == "toxin_plant"
    assert any("toxic plants" in p.lower() for p in hint.boost_title_patterns)


def test_human_medication_ingestion():
    hint = detect_intent("狗误食了布洛芬")
    assert hint is not None
    assert hint.label == "toxin_medication"
    assert any("human medications" in p.lower() for p in hint.boost_title_patterns)


def test_foreign_object_ingestion():
    hint = detect_intent("狗吞了一只袜子")
    assert hint is not None
    assert hint.label == "foreign_object"


def test_ingestion_without_target_returns_none():
    # Verb matches but no substance keyword — stay in default retrieval.
    assert detect_intent("狗吃了一顿") is None
    assert detect_intent("dog ate well today") is None


def test_first_match_wins_when_ambiguous():
    # Food pattern precedes plant pattern in the rule order.
    hint = detect_intent("狗吃了巧克力和百合")
    assert hint is not None
    assert hint.label == "toxin_food"
