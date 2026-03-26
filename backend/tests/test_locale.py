# backend/tests/test_locale.py
from app.agents.locale import t, detect_language


def test_t_returns_chinese_by_default():
    assert "CozyPup" in t("base_system_prompt", "zh")
    assert "宠物健康助手" in t("base_system_prompt", "zh")


def test_t_returns_english():
    result = t("base_system_prompt", "en")
    assert "CozyPup" in result
    assert "专业的宠物健康助手" not in result
    assert "pet health assistant" in result


def test_t_unknown_key_returns_key():
    assert t("nonexistent_key", "zh") == "nonexistent_key"
    assert t("nonexistent_key", "en") == "nonexistent_key"


def test_t_fallback_to_zh():
    """Unknown language falls back to zh."""
    result = t("base_system_prompt", "ja")
    assert "CozyPup" in result
    assert "宠物健康助手" in result


def test_detect_language_chinese():
    assert detect_language("三妹今天吃了狗粮") == "zh"


def test_detect_language_english():
    assert detect_language("My dog ate kibble today") == "en"


def test_detect_language_mixed():
    """Mixed content with CJK chars → zh."""
    assert detect_language("三妹 ate food today") == "zh"


def test_t_tool_decision_tree():
    zh = t("tool_decision_tree", "zh")
    assert "工具选择指南" in zh
    en = t("tool_decision_tree", "en")
    assert "Tool Selection Guide" in en
    assert "工具选择指南" not in en


def test_t_emergency_hint():
    zh = t("emergency_hint", "zh")
    assert "检测到" in zh
    en = t("emergency_hint", "en")
    assert "detected" in en
    assert "检测到" not in en
