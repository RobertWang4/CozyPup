"""Tests for calendar_event ↔ embedding sync."""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _fake_event():
    event = MagicMock()
    event.id = uuid.uuid4()
    event.user_id = uuid.uuid4()
    event.pet_id = uuid.uuid4()
    event.event_date = date(2026, 4, 20)
    event.title = "呕吐"
    event.raw_text = "早上吐了两次"
    event.notes = None
    event.category = MagicMock()
    event.category.value = "abnormal"
    return event


@pytest.mark.asyncio
async def test_sync_event_embedding_upserts():
    """sync_event_embedding deletes old rows then inserts fresh embedding."""
    event = _fake_event()

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__.return_value = mock_db
    mock_session_cm.__aexit__.return_value = None

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = event
    mock_db.execute.return_value = scalar_result

    with patch("app.rag.event_sync.async_session", return_value=mock_session_cm), \
         patch("app.rag.event_sync.embed_text", AsyncMock(return_value=[0.2] * 1536)):
        from app.rag.event_sync import sync_event_embedding
        await sync_event_embedding(event.id)

    # One SELECT + one DELETE
    assert mock_db.execute.call_count == 2
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()

    added = mock_db.add.call_args[0][0]
    assert added.source_id == event.id
    assert added.embedding == [0.2] * 1536
    assert "呕吐" in added.content


@pytest.mark.asyncio
async def test_sync_event_embedding_swallows_errors():
    """Failures never raise — derived data is best-effort."""
    with patch("app.rag.event_sync.async_session", side_effect=Exception("db down")):
        from app.rag.event_sync import sync_event_embedding
        await sync_event_embedding(uuid.uuid4())  # must not raise


@pytest.mark.asyncio
async def test_delete_event_embedding():
    mock_db = AsyncMock()
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__.return_value = mock_db
    mock_session_cm.__aexit__.return_value = None

    with patch("app.rag.event_sync.async_session", return_value=mock_session_cm):
        from app.rag.event_sync import delete_event_embedding
        await delete_event_embedding(uuid.uuid4())

    mock_db.execute.assert_called_once()
    mock_db.commit.assert_called_once()
