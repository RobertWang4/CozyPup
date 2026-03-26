"""Tests for the deterministic pre-processor."""

import uuid
from datetime import date
from types import SimpleNamespace

from app.agents.pre_processor import pre_process, format_actions_for_prompt, _resolve_date, _resolve_pets


def _make_pet(name, pet_id=None):
    return SimpleNamespace(id=pet_id or uuid.uuid4(), name=name)


class TestResolveDate:
    def test_today(self):
        assert _resolve_date("今天吃了狗粮", date(2026, 3, 22)) == date(2026, 3, 22)

    def test_tomorrow(self):
        assert _resolve_date("明天去公园", date(2026, 3, 22)) == date(2026, 3, 23)

    def test_yesterday(self):
        assert _resolve_date("昨天吐了", date(2026, 3, 22)) == date(2026, 3, 21)

    def test_explicit_date(self):
        assert _resolve_date("3月25号去看医生", date(2026, 3, 22)) == date(2026, 3, 25)

    def test_default_today(self):
        assert _resolve_date("吃了狗粮", date(2026, 3, 22)) == date(2026, 3, 22)


class TestResolvePets:
    def test_single_pet(self):
        pets = [_make_pet("Buddy")]
        result = _resolve_pets("吃了狗粮", pets)
        assert len(result) == 1
        assert result[0][1] == "Buddy"

    def test_mentioned_by_name(self):
        pets = [_make_pet("Winnie"), _make_pet("Summer")]
        result = _resolve_pets("Winnie吃了200克", pets)
        assert len(result) == 1
        assert result[0][1] == "Winnie"

    def test_ambiguous_returns_all(self):
        pets = [_make_pet("Winnie"), _make_pet("Summer")]
        result = _resolve_pets("吃了狗粮", pets)
        assert len(result) == 2


class TestPreProcess:
    def test_diet_detection(self):
        pets = [_make_pet("豆豆")]
        actions = pre_process("豆豆今天吃了200克狗粮", pets, today=date(2026, 3, 22))
        calendar_actions = [a for a in actions if a.tool_name == "create_calendar_event"]
        assert len(calendar_actions) == 1
        assert calendar_actions[0].arguments["category"] == "diet"
        assert calendar_actions[0].arguments["event_date"] == "2026-03-22"
        assert calendar_actions[0].confidence >= 0.8

    def test_abnormal_detection(self):
        pets = [_make_pet("维尼")]
        actions = pre_process("维尼今天吐了", pets, today=date(2026, 3, 22))
        assert len(actions) == 1
        assert actions[0].arguments["category"] == "abnormal"

    def test_daily_detection(self):
        pets = [_make_pet("Buddy")]
        actions = pre_process("遛狗了", pets, today=date(2026, 3, 22))
        assert len(actions) == 1
        assert actions[0].arguments["category"] == "daily"

    def test_vaccine_detection(self):
        pets = [_make_pet("Buddy")]
        actions = pre_process("今天打了疫苗", pets, today=date(2026, 3, 22))
        assert len(actions) == 1
        assert actions[0].arguments["category"] == "vaccine"

    def test_question_skips_calendar(self):
        pets = [_make_pet("维尼")]
        actions = pre_process("维尼上次吐是什么时候？", pets, today=date(2026, 3, 22))
        # Questions should NOT produce calendar event actions
        calendar_actions = [a for a in actions if a.tool_name == "create_calendar_event"]
        assert len(calendar_actions) == 0

    def test_pure_chat_returns_empty(self):
        pets = [_make_pet("Buddy")]
        actions = pre_process("你好", pets, today=date(2026, 3, 22))
        assert len(actions) == 0

    def test_multi_pet_no_name_creates_shared_event(self):
        """When no pet name is mentioned with multiple pets, create one shared event."""
        pets = [_make_pet("Winnie"), _make_pet("Summer")]
        actions = pre_process("吃了狗粮", pets, today=date(2026, 3, 22))
        calendar_actions = [a for a in actions if a.tool_name == "create_calendar_event"]
        assert len(calendar_actions) == 1
        assert "pet_id" not in calendar_actions[0].arguments

    def test_tomorrow_date(self):
        pets = [_make_pet("Buddy")]
        actions = pre_process("明天去公园散步", pets, today=date(2026, 3, 22))
        assert len(actions) == 1
        assert actions[0].arguments["event_date"] == "2026-03-23"


class TestFormatActionsForPrompt:
    def test_formats_high_confidence(self):
        from app.agents.pre_processor import SuggestedAction
        actions = [
            SuggestedAction("create_calendar_event", {"pet_id": "abc", "title": "吃了"}, 0.9),
        ]
        result = format_actions_for_prompt(actions)
        assert "Suggested actions" in result
        assert "create_calendar_event" in result

    def test_includes_medium_confidence(self):
        from app.agents.pre_processor import SuggestedAction
        actions = [
            SuggestedAction("create_pet", {"name": "Luna"}, 0.6),
        ]
        result = format_actions_for_prompt(actions)
        assert "create_pet" in result
        assert "置信度: 0.6" in result

    def test_skips_low_confidence(self):
        from app.agents.pre_processor import SuggestedAction
        actions = [
            SuggestedAction("create_pet", {"name": "Luna"}, 0.4),
        ]
        result = format_actions_for_prompt(actions)
        assert result == ""

    def test_empty_actions(self):
        result = format_actions_for_prompt([])
        assert result == ""
