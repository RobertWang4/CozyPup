"""Tests for the Summary Agent."""

import json
import uuid
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.summary_agent import SummaryAgent


def _make_litellm_response(content: str):
    """Build a mock LiteLLM completion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


def _make_pet(name: str, pet_id=None, species_val="dog", breed="Mixed"):
    """Create a mock Pet object."""
    pet = MagicMock()
    pet.id = pet_id or uuid.uuid4()
    pet.name = name
    pet.species.value = species_val
    pet.breed = breed
    pet.weight = 10.0
    return pet


def _make_chat(role_val: str, content: str):
    """Create a mock Chat object."""
    chat = MagicMock()
    chat.role.value = role_val
    chat.content = content
    chat.created_at = datetime.now()
    return chat


def _make_scalars_result(items):
    """Create a mock scalars().all() result chain."""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items
    mock_scalars.first.return_value = items[0] if items else None
    mock_result.scalars.return_value = mock_scalars
    return mock_result


def _make_empty_scalars():
    """Create a mock scalars() with no results."""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_scalars.first.return_value = None
    mock_result.scalars.return_value = mock_scalars
    return mock_result


@pytest.mark.asyncio
class TestSummaryAgent:
    """Test SummaryAgent with mocked DB and LiteLLM."""

    def _base_context(self, db_mock, pets=None):
        return {
            "db": db_mock,
            "user_id": uuid.uuid4(),
            "session_id": uuid.uuid4(),
            "pets": pets or [_make_pet("Buddy")],
        }

    @patch("app.agents.summary_agent.litellm")
    async def test_creates_events_from_valid_response(self, mock_litellm):
        """Valid LLM JSON events should create CalendarEvents."""
        buddy = _make_pet("Buddy")
        chats = [
            _make_chat("user", "Buddy didn't eat much this morning"),
            _make_chat("assistant", "That can happen. Monitor his appetite."),
        ]

        events_json = json.dumps([{
            "pet_name": "Buddy",
            "event_date": date.today().isoformat(),
            "title": "Ate less than usual at breakfast",
            "category": "diet",
            "raw_text": "Buddy didn't eat much this morning",
        }])

        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(events_json)
        )

        db = AsyncMock()
        # First execute: fetch chats; second execute: duplicate check
        db.execute = AsyncMock(side_effect=[
            _make_scalars_result(chats),
            _make_empty_scalars(),
        ])

        agent = SummaryAgent()
        ctx = self._base_context(db, pets=[buddy])
        result = await agent._run("summarize", ctx)

        assert result["events_created"] == 1
        assert result["reminders_created"] == 0
        assert len(result["cards"]) == 1
        assert result["cards"][0]["type"] == "record"
        assert result["cards"][0]["pet_name"] == "Buddy"
        assert result["cards"][0]["category"] == "diet"
        assert db.add.call_count == 1  # 1 event, no reminder
        db.flush.assert_awaited_once()

    @patch("app.agents.summary_agent.litellm")
    async def test_dedup_skips_existing_event(self, mock_litellm):
        """Should not create duplicate events (same pet+date+category+title)."""
        buddy = _make_pet("Buddy")
        chats = [_make_chat("user", "Buddy vomited")]

        events_json = json.dumps([{
            "pet_name": "Buddy",
            "event_date": date.today().isoformat(),
            "title": "Vomited after eating",
            "category": "abnormal",
            "raw_text": "Buddy vomited",
        }])

        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(events_json)
        )

        # Duplicate check returns existing event
        existing_event = MagicMock()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _make_scalars_result(chats),       # fetch chats
            _make_scalars_result([existing_event]),  # dup found
        ])

        agent = SummaryAgent()
        ctx = self._base_context(db, pets=[buddy])
        result = await agent._run("summarize", ctx)

        assert result["events_created"] == 0
        assert result["reminders_created"] == 0
        assert len(result["cards"]) == 0

    @patch("app.agents.summary_agent.litellm")
    async def test_creates_reminder_for_abnormal_category(self, mock_litellm):
        """Abnormal events should also create a follow-up Reminder."""
        buddy = _make_pet("Buddy")
        chats = [_make_chat("user", "Buddy has been limping all day")]

        events_json = json.dumps([{
            "pet_name": "Buddy",
            "event_date": date.today().isoformat(),
            "title": "Limping on right front leg",
            "category": "abnormal",
            "raw_text": "Buddy has been limping all day",
        }])

        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(events_json)
        )

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _make_scalars_result(chats),
            _make_empty_scalars(),
        ])

        agent = SummaryAgent()
        ctx = self._base_context(db, pets=[buddy])
        result = await agent._run("summarize", ctx)

        assert result["events_created"] == 1
        assert result["reminders_created"] == 1
        assert db.add.call_count == 2  # 1 event + 1 reminder

    @patch("app.agents.summary_agent.litellm")
    async def test_creates_reminder_for_medical_category(self, mock_litellm):
        """Medical events should also create a follow-up Reminder."""
        buddy = _make_pet("Buddy")
        chats = [_make_chat("user", "Took Buddy to the vet for a checkup")]

        events_json = json.dumps([{
            "pet_name": "Buddy",
            "event_date": date.today().isoformat(),
            "title": "Vet checkup completed",
            "category": "medical",
            "raw_text": "Took Buddy to the vet for a checkup",
        }])

        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(events_json)
        )

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _make_scalars_result(chats),
            _make_empty_scalars(),
        ])

        agent = SummaryAgent()
        ctx = self._base_context(db, pets=[buddy])
        result = await agent._run("summarize", ctx)

        assert result["events_created"] == 1
        assert result["reminders_created"] == 1

    @patch("app.agents.summary_agent.litellm")
    async def test_skips_unmatched_pet_names(self, mock_litellm):
        """Events with unknown pet names should be skipped gracefully."""
        buddy = _make_pet("Buddy")
        chats = [_make_chat("user", "Max ate something weird")]

        events_json = json.dumps([{
            "pet_name": "Max",
            "event_date": date.today().isoformat(),
            "title": "Ate something unusual",
            "category": "diet",
            "raw_text": "Max ate something weird",
        }])

        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(events_json)
        )

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _make_scalars_result(chats),
        ])

        agent = SummaryAgent()
        ctx = self._base_context(db, pets=[buddy])
        result = await agent._run("summarize", ctx)

        assert result["events_created"] == 0
        assert len(result["cards"]) == 0

    @patch("app.agents.summary_agent.litellm")
    async def test_handles_malformed_json(self, mock_litellm):
        """Malformed LLM response should not crash, return zero events."""
        chats = [_make_chat("user", "Hello")]

        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response("this is not json at all")
        )

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _make_scalars_result(chats),
        ])

        agent = SummaryAgent()
        ctx = self._base_context(db)
        result = await agent._run("summarize", ctx)

        assert result["events_created"] == 0
        assert result["summary_text"] == "Could not parse summary from the conversation."

    @patch("app.agents.summary_agent.litellm")
    async def test_handles_llm_exception(self, mock_litellm):
        """LiteLLM raising an exception should not crash."""
        chats = [_make_chat("user", "Hello")]

        mock_litellm.acompletion = AsyncMock(side_effect=Exception("API down"))

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _make_scalars_result(chats),
        ])

        agent = SummaryAgent()
        ctx = self._base_context(db)
        result = await agent._run("summarize", ctx)

        assert result["events_created"] == 0
        assert result["summary_text"] == "Could not parse summary from the conversation."

    @patch("app.agents.summary_agent.litellm")
    async def test_empty_session_returns_no_events(self, mock_litellm):
        """Session with no messages should return early."""
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_empty_scalars())

        agent = SummaryAgent()
        ctx = self._base_context(db)
        result = await agent._run("summarize", ctx)

        assert result["events_created"] == 0
        assert "No messages" in result["summary_text"]
        mock_litellm.acompletion.assert_not_called()

    @patch("app.agents.summary_agent.litellm")
    async def test_case_insensitive_pet_matching(self, mock_litellm):
        """Pet name matching should be case-insensitive."""
        buddy = _make_pet("Buddy")
        chats = [_make_chat("user", "buddy ate well today")]

        events_json = json.dumps([{
            "pet_name": "buddy",
            "event_date": date.today().isoformat(),
            "title": "Good appetite today",
            "category": "diet",
            "raw_text": "buddy ate well today",
        }])

        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(events_json)
        )

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _make_scalars_result(chats),
            _make_empty_scalars(),
        ])

        agent = SummaryAgent()
        ctx = self._base_context(db, pets=[buddy])
        result = await agent._run("summarize", ctx)

        assert result["events_created"] == 1
        assert result["cards"][0]["pet_name"] == "Buddy"

    @patch("app.agents.summary_agent.litellm")
    async def test_llm_returns_empty_array(self, mock_litellm):
        """Empty array from LLM means no events found."""
        chats = [_make_chat("user", "Hello, how are you?")]

        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response("[]")
        )

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _make_scalars_result(chats),
        ])

        agent = SummaryAgent()
        ctx = self._base_context(db)
        result = await agent._run("summarize", ctx)

        assert result["events_created"] == 0
        assert result["summary_text"] == "No health events found to record."

    @patch("app.agents.summary_agent.litellm")
    async def test_multiple_events_multiple_pets(self, mock_litellm):
        """Should handle multiple events across multiple pets."""
        buddy = _make_pet("Buddy")
        luna = _make_pet("Luna", species_val="cat", breed="Persian")
        chats = [
            _make_chat("user", "Buddy ate well. Luna has been sneezing."),
            _make_chat("assistant", "Monitor Luna's sneezing."),
        ]

        events_json = json.dumps([
            {
                "pet_name": "Buddy",
                "event_date": date.today().isoformat(),
                "title": "Good appetite",
                "category": "diet",
                "raw_text": "Buddy ate well",
            },
            {
                "pet_name": "Luna",
                "event_date": date.today().isoformat(),
                "title": "Frequent sneezing",
                "category": "abnormal",
                "raw_text": "Luna has been sneezing",
            },
        ])

        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(events_json)
        )

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _make_scalars_result(chats),
            _make_empty_scalars(),  # dup check for Buddy event
            _make_empty_scalars(),  # dup check for Luna event
        ])

        agent = SummaryAgent()
        ctx = self._base_context(db, pets=[buddy, luna])
        result = await agent._run("summarize", ctx)

        assert result["events_created"] == 2
        assert result["reminders_created"] == 1  # Luna's abnormal event
        assert len(result["cards"]) == 2
        assert db.add.call_count == 3  # 2 events + 1 reminder

    @patch("app.agents.summary_agent.litellm")
    async def test_invalid_category_defaults_to_daily(self, mock_litellm):
        """Invalid category from LLM should default to 'daily'."""
        buddy = _make_pet("Buddy")
        chats = [_make_chat("user", "Buddy played in the park")]

        events_json = json.dumps([{
            "pet_name": "Buddy",
            "event_date": date.today().isoformat(),
            "title": "Played in the park",
            "category": "invalid_category",
            "raw_text": "Buddy played in the park",
        }])

        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(events_json)
        )

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _make_scalars_result(chats),
            _make_empty_scalars(),
        ])

        agent = SummaryAgent()
        ctx = self._base_context(db, pets=[buddy])
        result = await agent._run("summarize", ctx)

        assert result["events_created"] == 1
        assert result["cards"][0]["category"] == "daily"

    @patch("app.agents.summary_agent.litellm")
    async def test_handles_non_array_response(self, mock_litellm):
        """LLM returning a dict instead of array should be handled."""
        chats = [_make_chat("user", "Hello")]

        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response('{"error": "something"}')
        )

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _make_scalars_result(chats),
        ])

        agent = SummaryAgent()
        ctx = self._base_context(db)
        result = await agent._run("summarize", ctx)

        assert result["events_created"] == 0
        assert result["summary_text"] == "Summary returned unexpected format."

    @patch("app.agents.summary_agent.litellm")
    async def test_handles_markdown_code_fences(self, mock_litellm):
        """LLM wrapping JSON in ```json fences should still work."""
        buddy = _make_pet("Buddy")
        chats = [_make_chat("user", "Buddy ate well")]

        events_json = '```json\n' + json.dumps([{
            "pet_name": "Buddy",
            "event_date": date.today().isoformat(),
            "title": "Good appetite",
            "category": "diet",
            "raw_text": "Buddy ate well",
        }]) + '\n```'

        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(events_json)
        )

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _make_scalars_result(chats),
            _make_empty_scalars(),
        ])

        agent = SummaryAgent()
        ctx = self._base_context(db, pets=[buddy])
        result = await agent._run("summarize", ctx)

        assert result["events_created"] == 1
