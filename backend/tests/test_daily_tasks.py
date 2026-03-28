"""Tests for daily tasks feature."""
import uuid
from datetime import date
from unittest.mock import MagicMock

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
