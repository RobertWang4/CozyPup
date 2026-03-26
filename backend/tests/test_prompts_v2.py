"""Tests for the V2 prompt builder (cache-friendly ordering)."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.agents.locale import t
from app.agents.prompts_v2 import (
    build_messages,
    build_system_prompt,
    _build_pet_context,
    _build_summary_section,
)
from app.agents.locale import t


# ---------------------------------------------------------------------------
# Helpers — fake pet objects that mirror SQLAlchemy Pet model attributes
# ---------------------------------------------------------------------------

class FakeSpecies:
    def __init__(self, value: str):
        self.value = value


def _make_pet(**overrides):
    defaults = dict(
        id="pet-001",
        name="豆豆",
        species=FakeSpecies("dog"),
        species_locked=False,
        breed="柴犬",
        weight=10.5,
        birthday=date(2023, 6, 15),
        profile_md=None,
        profile=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# build_system_prompt — ordering tests
# ---------------------------------------------------------------------------

class TestBuildSystemPrompt:
    def test_static_content_comes_first(self):
        """Base prompt and tool decision tree must appear before any dynamic content."""
        prompt = build_system_prompt(
            pets=[_make_pet()],
            session_summary={"topics": ["散步"], "key_facts": ["今天走了3公里"], "pending": None, "mood": "happy"},
            emergency_hint="⚠️ 检测到紧急关键词",
            preprocessor_hints=["可能要记录事件"],
            today="2026-03-24",
        )

        base_idx = prompt.index("CozyPup")
        tool_idx = prompt.index("工具选择指南")
        pet_idx = prompt.index("用户的宠物")
        summary_idx = prompt.index("今日对话摘要")
        emergency_idx = prompt.index("紧急关键词")
        hint_idx = prompt.index("系统检测到")

        # Order: base < tool_guide < pets < summary < emergency < hints
        assert base_idx < tool_idx
        assert tool_idx < pet_idx
        assert pet_idx < summary_idx
        assert summary_idx < emergency_idx
        assert emergency_idx < hint_idx

    def test_minimal_prompt_no_pets(self):
        """With no pets, prompt should still contain base + tool guide + no-pet message."""
        prompt = build_system_prompt()
        assert "CozyPup" in prompt
        assert "工具选择指南" in prompt
        assert "用户还没有添加宠物" in prompt

    def test_today_date_included(self):
        prompt = build_system_prompt(today="2026-03-24")
        assert "今天日期: 2026-03-24" in prompt

    def test_today_date_omitted_when_empty(self):
        prompt = build_system_prompt(today="")
        assert "今天日期" not in prompt

    def test_no_emergency_hint_when_none(self):
        prompt = build_system_prompt()
        assert "检测到可能的紧急关键词" not in prompt

    def test_no_hints_section_when_none(self):
        prompt = build_system_prompt()
        assert "系统检测到" not in prompt

    def test_preprocessor_hints_formatted(self):
        prompt = build_system_prompt(preprocessor_hints=["hint_a", "hint_b"])
        assert "- hint_a" in prompt
        assert "- hint_b" in prompt

    def test_session_summary_omitted_when_none(self):
        prompt = build_system_prompt(session_summary=None)
        assert "今日对话摘要" not in prompt


# ---------------------------------------------------------------------------
# Pet context
# ---------------------------------------------------------------------------

class TestPetContext:
    def test_basic_pet_info(self):
        pet = _make_pet()
        ctx = _build_pet_context([pet])
        assert "豆豆" in ctx
        assert "pet-001" in ctx
        assert "dog" in ctx
        assert "柴犬" in ctx
        assert "10.5kg" in ctx
        assert "2023-06-15" in ctx

    def test_profile_md_included(self):
        pet = _make_pet(profile_md="# 豆豆档案\n性格活泼")
        ctx = _build_pet_context([pet])
        assert "豆豆的档案" in ctx
        assert "性格活泼" in ctx

    def test_profile_json_fallback(self):
        pet = _make_pet(profile={"allergies": "鸡肉"})
        ctx = _build_pet_context([pet])
        assert "鸡肉" in ctx
        assert "档案:" in ctx

    def test_profile_md_takes_priority_over_json(self):
        pet = _make_pet(profile_md="narrative profile", profile={"key": "val"})
        ctx = _build_pet_context([pet])
        assert "narrative profile" in ctx
        # JSON fallback should NOT appear when profile_md exists
        assert '"key"' not in ctx

    def test_multiple_pets(self):
        pets = [
            _make_pet(id="p1", name="豆豆"),
            _make_pet(id="p2", name="花花", species=FakeSpecies("cat"), breed="英短"),
        ]
        ctx = _build_pet_context(pets)
        assert "豆豆" in ctx
        assert "花花" in ctx
        assert "cat" in ctx

    def test_optional_fields_missing(self):
        """Pet with no breed/weight/birthday should not crash."""
        pet = _make_pet(breed="", weight=None, birthday=None)
        ctx = _build_pet_context([pet])
        assert "豆豆" in ctx
        assert "品种" not in ctx
        assert "体重" not in ctx
        assert "生日" not in ctx

    def test_dict_pets(self):
        """Should also work with dict-style pets (not ORM objects)."""
        pet_dict = {
            "id": "d1",
            "name": "小白",
            "species": "cat",
            "breed": "布偶",
            "weight": 5.0,
            "birthday": None,
            "profile_md": None,
            "profile": None,
        }
        ctx = _build_pet_context([pet_dict])
        assert "小白" in ctx
        assert "布偶" in ctx


# ---------------------------------------------------------------------------
# Session summary
# ---------------------------------------------------------------------------

class TestSummarySection:
    def test_full_summary(self):
        summary = {
            "topics": ["疫苗", "散步"],
            "key_facts": ["三针疫苗已完成", "每天散步30分钟"],
            "pending": "预约驱虫",
            "mood": "happy",
        }
        section = _build_summary_section(summary)
        assert "今日对话摘要" in section
        assert "疫苗" in section
        assert "散步" in section
        assert "三针疫苗已完成" in section
        assert "预约驱虫" in section
        assert "用户情绪: happy" in section

    def test_neutral_mood_hidden(self):
        summary = {"topics": [], "key_facts": [], "pending": None, "mood": "neutral"}
        section = _build_summary_section(summary)
        assert "用户情绪" not in section

    def test_unknown_mood_hidden(self):
        summary = {"topics": [], "key_facts": [], "pending": None, "mood": "unknown"}
        section = _build_summary_section(summary)
        assert "用户情绪" not in section

    def test_empty_summary(self):
        summary = {"topics": [], "key_facts": [], "pending": None, "mood": "neutral"}
        section = _build_summary_section(summary)
        assert "今日对话摘要" in section
        # Should not contain topics/facts/pending sections
        assert "话题:" not in section
        assert "重要信息:" not in section
        assert "待办:" not in section


# ---------------------------------------------------------------------------
# build_messages
# ---------------------------------------------------------------------------

class TestBuildMessages:
    def test_text_only(self):
        recent = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好呀！"},
        ]
        msgs = build_messages(recent, "豆豆今天吃了吗")
        assert len(msgs) == 3
        assert msgs[0] == {"role": "user", "content": "你好"}
        assert msgs[1] == {"role": "assistant", "content": "你好呀！"}
        assert msgs[2] == {"role": "user", "content": "豆豆今天吃了吗"}

    def test_empty_history(self):
        msgs = build_messages([], "hello")
        assert len(msgs) == 1
        assert msgs[0] == {"role": "user", "content": "hello"}

    def test_missing_role_defaults_to_user(self):
        msgs = build_messages([{"content": "test"}], "hi")
        assert msgs[0]["role"] == "user"

    def test_missing_content_defaults_to_empty(self):
        msgs = build_messages([{"role": "user"}], "hi")
        assert msgs[0]["content"] == ""

    def test_images_creates_multimodal_content(self):
        """When images are provided, user message should be multimodal."""
        import base64

        fake_img = base64.b64encode(b"fake-image-data").decode()
        msgs = build_messages([], "看看这张照片", images=[fake_img])

        assert len(msgs) == 1
        content = msgs[0]["content"]
        assert isinstance(content, list)
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "看看这张照片"
        assert content[1]["type"] == "image_url"
        assert "data:image/jpeg;base64," in content[1]["image_url"]["url"]

    def test_multiple_images(self):
        import base64

        fake_img = base64.b64encode(b"img").decode()
        msgs = build_messages([], "两张照片", images=[fake_img, fake_img])

        content = msgs[0]["content"]
        assert len(content) == 3  # 1 text + 2 images


# ---------------------------------------------------------------------------
# Cache-friendliness: static prefix is identical across calls
# ---------------------------------------------------------------------------

class TestCacheFriendliness:
    def test_static_prefix_stable(self):
        """Two calls with same pets but different dynamic args should share a prefix."""
        prompt_a = build_system_prompt(
            pets=[_make_pet()],
            session_summary={"topics": ["A"], "key_facts": [], "pending": None, "mood": "neutral"},
            emergency_hint="emergency A",
            today="2026-03-24",
        )
        prompt_b = build_system_prompt(
            pets=[_make_pet()],
            session_summary={"topics": ["B"], "key_facts": [], "pending": None, "mood": "neutral"},
            emergency_hint="emergency B",
            today="2026-03-24",
        )

        # The static prefix (base prompt + tool guide + pet context + date)
        # should be identical; only the summary and emergency sections differ.
        prefix_a = prompt_a.split("今日对话摘要")[0]
        prefix_b = prompt_b.split("今日对话摘要")[0]
        assert prefix_a == prefix_b
