import re
from app.agents.locale import t, detect_language
from app.agents.prompts_v2 import build_system_prompt
from app.agents.tool_guide import get_tool_decision_tree
from app.agents.emergency import build_emergency_hint
from app.agents.tools import get_tool_definitions


def test_english_system_prompt_has_no_chinese():
    prompt = build_system_prompt(pets=[], today="2026-03-26", lang="en")
    cjk = re.findall(r"[\u4e00-\u9fff]", prompt)
    assert len(cjk) == 0, f"Found Chinese chars in English prompt: {''.join(cjk[:20])}"


def test_chinese_system_prompt_works():
    prompt = build_system_prompt(pets=[], today="2026-03-26", lang="zh")
    assert "CozyPup" in prompt
    assert "宠物健康助手" in prompt


def test_english_system_prompt_has_key_content():
    prompt = build_system_prompt(pets=[], today="2026-03-26", lang="en")
    assert "CozyPup" in prompt
    assert "pet health assistant" in prompt
    assert "Tool Selection Guide" in prompt
    assert "2026-03-26" in prompt


def test_tool_decision_tree_english():
    tree = get_tool_decision_tree("en")
    assert "Tool Selection Guide" in tree
    assert "工具选择指南" not in tree


def test_emergency_hint_english():
    hint = build_emergency_hint(["seizure"], lang="en")
    assert "emergency" in hint.lower()
    assert "seizure" in hint
    assert "检测到" not in hint


def test_emergency_hint_chinese():
    hint = build_emergency_hint(["抽搐"], lang="zh")
    assert "检测到" in hint
    assert "抽搐" in hint


def test_detect_language_used_as_fallback():
    assert detect_language("hello") == "en"
    assert detect_language("你好") == "zh"


def test_tool_definitions_english():
    tools = get_tool_definitions("en")
    for tool in tools:
        desc = tool["function"]["description"]
        # English descriptions should not contain Chinese
        cjk = re.findall(r"[\u4e00-\u9fff]", desc)
        assert len(cjk) == 0, f"Tool {tool['function']['name']} has Chinese in English desc: {desc[:50]}"


def test_tool_definitions_chinese_unchanged():
    tools = get_tool_definitions("zh")
    # Should still have Chinese descriptions
    first_desc = tools[0]["function"]["description"]
    assert any(ord(c) > 0x4e00 for c in first_desc), "Chinese tool descriptions should contain CJK chars"


def test_system_prompt_with_pets_english():
    """Test that pet context is also in English."""
    class FakePet:
        def __init__(self):
            self.id = "test-id"
            self.name = "Buddy"
            self.species = type("S", (), {"value": "dog"})()
            self.species_locked = True
            self.breed = "Golden Retriever"
            self.weight = 30.0
            self.birthday = None
            self.profile = {"gender": "male", "gender_locked": True}
            self.profile_md = None

    prompt = build_system_prompt(pets=[FakePet()], today="2026-03-26", lang="en")
    assert "User's Pets" in prompt
    assert "gender=male" in prompt
    assert "species=🔒locked" in prompt
    assert "breed=Golden Retriever" in prompt
    # Should NOT have Chinese labels
    assert "性别" not in prompt
    assert "品种" not in prompt
