"""Tests for daily tasks feature."""
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.models import DailyTask, DailyTaskCompletion, TaskType


def test_daily_task_model_fields():
    task = DailyTask(
        id=uuid.uuid4(), user_id=uuid.uuid4(), title="遛狗",
        type=TaskType.routine, daily_target=2, active=True,
    )
    assert task.title == "遛狗"
    assert task.type == TaskType.routine
    assert task.daily_target == 2
    assert task.active is True
    assert task.pet_id is None
    assert task.start_date is None
    assert task.end_date is None


def test_daily_task_completion_model_fields():
    task_id = uuid.uuid4()
    comp = DailyTaskCompletion(
        id=uuid.uuid4(), task_id=task_id, date=date(2026, 3, 28), count=1,
    )
    assert comp.task_id == task_id
    assert comp.date == date(2026, 3, 28)
    assert comp.count == 1


def test_task_type_enum():
    assert TaskType.routine.value == "routine"
    assert TaskType.special.value == "special"


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_get_today_tasks_empty(mock_db):
    from app.routers.tasks import _get_today_tasks
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute.return_value = mock_result
    result = await _get_today_tasks(mock_db, uuid.uuid4(), date(2026, 3, 28))
    assert result["tasks"] == []
    assert result["all_completed"] is True
