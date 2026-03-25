import pytest
import json
from unittest.mock import AsyncMock, patch
from dataclasses import dataclass
from app.agents.speculative import (
    speculative_execute, match_speculative, commit_or_rollback,
    SpeculativeResult, DESTRUCTIVE_TOOLS,
)


@dataclass
class MockAction:
    tool_name: str
    arguments: dict
    confidence: float
    confirm_description: str = ""


@pytest.mark.asyncio
async def test_speculative_execute_high_confidence():
    """High confidence non-destructive action gets executed."""
    action = MockAction(
        tool_name="create_calendar_event",
        arguments={"pet_id": "abc", "event_date": "2026-03-24", "title": "吃狗粮", "category": "diet"},
        confidence=0.9,
    )

    mock_db = AsyncMock()
    mock_result = {"success": True, "card": {"type": "record"}}

    with patch("app.agents.speculative.validate_tool_args", return_value=[]), \
         patch("app.agents.speculative.execute_tool", new_callable=AsyncMock, return_value=mock_result):
        results = await speculative_execute([action], mock_db, "user-1")

    assert len(results) == 1
    assert results[0].executed is True
    assert results[0].card is not None
    mock_db.commit.assert_not_called()  # Should NOT commit


@pytest.mark.asyncio
async def test_speculative_skips_low_confidence():
    """Low confidence actions are skipped."""
    action = MockAction(
        tool_name="create_calendar_event",
        arguments={"pet_id": "abc"},
        confidence=0.5,
    )

    with patch("app.agents.speculative.execute_tool", new_callable=AsyncMock) as mock_exec:
        results = await speculative_execute([action], AsyncMock(), "user-1")

    assert len(results) == 0
    mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_speculative_skips_destructive():
    """Destructive tools are never speculatively executed."""
    for tool in DESTRUCTIVE_TOOLS:
        action = MockAction(tool_name=tool, arguments={}, confidence=0.95)
        with patch("app.agents.speculative.execute_tool", new_callable=AsyncMock) as mock_exec:
            results = await speculative_execute([action], AsyncMock(), "user-1")
        assert len(results) == 0
        mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_speculative_execute_validation_failure():
    """Action with validation errors is not executed but recorded."""
    action = MockAction(
        tool_name="create_calendar_event",
        arguments={"pet_id": "bad-uuid"},
        confidence=0.9,
    )

    with patch("app.agents.speculative.validate_tool_args", return_value=["Invalid UUID"]), \
         patch("app.agents.speculative.execute_tool", new_callable=AsyncMock) as mock_exec:
        results = await speculative_execute([action], AsyncMock(), "user-1")

    assert len(results) == 1
    assert results[0].executed is False
    assert "Validation" in results[0].error
    mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_speculative_execute_tool_error():
    """Tool execution error is captured gracefully."""
    action = MockAction(
        tool_name="create_calendar_event",
        arguments={"pet_id": "abc", "event_date": "2026-03-24", "title": "test", "category": "diet"},
        confidence=0.9,
    )

    with patch("app.agents.speculative.validate_tool_args", return_value=[]), \
         patch("app.agents.speculative.execute_tool", new_callable=AsyncMock, side_effect=RuntimeError("DB error")):
        results = await speculative_execute([action], AsyncMock(), "user-1")

    assert len(results) == 1
    assert results[0].executed is False
    assert "DB error" in results[0].error


def test_match_speculative_hit():
    """Matching speculative result is found."""
    spec = SpeculativeResult(
        tool_name="create_calendar_event",
        arguments={"pet_id": "abc", "event_date": "2026-03-24", "category": "diet"},
        executed=True,
    )

    result = match_speculative(
        [spec],
        "create_calendar_event",
        {"pet_id": "abc", "event_date": "2026-03-24", "category": "diet", "title": "不同的title"},
    )
    assert result is spec  # Title difference is OK


def test_match_speculative_miss():
    """Non-matching speculative result returns None."""
    spec = SpeculativeResult(
        tool_name="create_calendar_event",
        arguments={"pet_id": "abc", "event_date": "2026-03-24", "category": "diet"},
        executed=True,
    )

    # Different pet_id
    result = match_speculative(
        [spec],
        "create_calendar_event",
        {"pet_id": "DIFFERENT", "event_date": "2026-03-24", "category": "diet"},
    )
    assert result is None


def test_match_speculative_skips_not_executed():
    """Non-executed speculative results are not matched."""
    spec = SpeculativeResult(
        tool_name="create_calendar_event",
        arguments={"pet_id": "abc", "category": "diet"},
        executed=False,
        error="Validation error",
    )

    result = match_speculative(
        [spec],
        "create_calendar_event",
        {"pet_id": "abc", "category": "diet"},
    )
    assert result is None


def test_match_speculative_different_tool():
    """Different tool name does not match."""
    spec = SpeculativeResult(
        tool_name="create_calendar_event",
        arguments={"pet_id": "abc"},
        executed=True,
    )

    result = match_speculative(
        [spec],
        "create_reminder",
        {"pet_id": "abc"},
    )
    assert result is None


@pytest.mark.asyncio
async def test_commit_on_match():
    """Matching results trigger commit."""
    spec = SpeculativeResult(
        tool_name="create_calendar_event",
        arguments={"pet_id": "abc", "category": "diet"},
        executed=True,
    )

    mock_db = AsyncMock()

    matched = await commit_or_rollback(
        [spec],
        [{"function": {"name": "create_calendar_event", "arguments": json.dumps({"pet_id": "abc", "category": "diet"})}}],
        mock_db,
    )

    assert len(matched) == 1
    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_rollback_on_mismatch():
    """Non-matching results trigger rollback."""
    spec = SpeculativeResult(
        tool_name="create_calendar_event",
        arguments={"pet_id": "abc", "category": "diet"},
        executed=True,
    )

    mock_db = AsyncMock()

    # LLM decided to do something completely different
    matched = await commit_or_rollback(
        [spec],
        [{"function": {"name": "create_reminder", "arguments": json.dumps({"pet_id": "abc"})}}],
        mock_db,
    )

    assert len(matched) == 0
    mock_db.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_commit_or_rollback_empty():
    """No speculative results means nothing to commit/rollback."""
    mock_db = AsyncMock()

    matched = await commit_or_rollback(
        [],
        [{"function": {"name": "create_calendar_event", "arguments": "{}"}}],
        mock_db,
    )

    assert len(matched) == 0
    mock_db.commit.assert_not_called()
    mock_db.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_rollback_partial_match():
    """If some specs match but others don't, rollback all."""
    spec1 = SpeculativeResult(
        tool_name="create_calendar_event",
        arguments={"pet_id": "abc", "category": "diet"},
        executed=True,
    )
    spec2 = SpeculativeResult(
        tool_name="create_calendar_event",
        arguments={"pet_id": "def", "category": "daily"},
        executed=True,
    )

    mock_db = AsyncMock()

    # LLM only confirmed one of the two
    matched = await commit_or_rollback(
        [spec1, spec2],
        [{"function": {"name": "create_calendar_event", "arguments": json.dumps({"pet_id": "abc", "category": "diet"})}}],
        mock_db,
    )

    assert len(matched) == 0  # All rolled back
    mock_db.rollback.assert_called_once()
    mock_db.commit.assert_not_called()
