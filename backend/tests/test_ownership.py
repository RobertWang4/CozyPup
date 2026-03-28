"""Test that tool handlers enforce ownership."""
import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.agents.tools import execute_tool


@pytest.fixture
def mock_db():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_create_event_rejects_unowned_pet(mock_db):
    result = await execute_tool(
        "create_calendar_event",
        {"pet_id": str(uuid.uuid4()), "event_date": "2026-03-27",
         "title": "Test", "category": "daily"},
        mock_db, uuid.uuid4(),
    )
    assert result["success"] is False
    assert "No valid pets" in result.get("error", "")


@pytest.mark.asyncio
async def test_update_pet_rejects_unowned(mock_db):
    result = await execute_tool(
        "update_pet_profile",
        {"pet_id": str(uuid.uuid4()), "info": {"weight": 5.0}},
        mock_db, uuid.uuid4(),
    )
    assert result["success"] is False


@pytest.mark.asyncio
async def test_delete_pet_rejects_unowned(mock_db):
    result = await execute_tool(
        "delete_pet", {"pet_id": str(uuid.uuid4())},
        mock_db, uuid.uuid4(),
    )
    assert result["success"] is False
