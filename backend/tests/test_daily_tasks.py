"""Tests for daily tasks feature."""
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.models import DailyTask, DailyTaskCompletion, TaskType
from app.agents.tools import execute_tool


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
async def test_create_daily_task_tool_routine(mock_db):
    pet_id = uuid.uuid4()
    mock_pet = MagicMock()
    mock_pet.id = pet_id
    mock_pet.name = "豆豆"
    mock_pet.color_hex = "E8835C"
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_pet
    mock_db.execute.return_value = mock_result
    result = await execute_tool("create_daily_task", {
        "title": "遛狗", "type": "routine", "daily_target": 2, "pet_id": str(pet_id),
    }, mock_db, uuid.uuid4())
    assert result["success"] is True
    assert result["title"] == "遛狗"
    assert result["daily_target"] == 2
    assert "card" in result


@pytest.mark.asyncio
async def test_create_daily_task_tool_special(mock_db):
    # No pet_id — don't need to mock pet lookup
    # But execute_tool may still call db.execute for flush, so set up return
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    result = await execute_tool("create_daily_task", {
        "title": "吃益生菌", "type": "special", "daily_target": 1,
        "start_date": "2026-03-28", "end_date": "2026-04-03",
    }, mock_db, uuid.uuid4())
    assert result["success"] is True
    assert result["type"] == "special"


@pytest.mark.asyncio
async def test_get_today_tasks_empty(mock_db):
    from app.routers.tasks import _get_today_tasks
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute.return_value = mock_result
    result = await _get_today_tasks(mock_db, uuid.uuid4(), date(2026, 3, 28))
    assert result["tasks"] == []
    assert result["all_completed"] is True


from app.agents.pre_processing import pre_process


def _make_pet(name: str):
    pet = MagicMock()
    pet.id = uuid.uuid4()
    pet.name = name
    return pet


def test_preprocess_detects_routine_task():
    pets = [_make_pet("豆豆")]
    actions = pre_process("帮我设置每天遛狗两次", pets, today=date(2026, 3, 28))
    task_actions = [a for a in actions if a.tool_name == "create_daily_task"]
    assert len(task_actions) >= 1
    assert task_actions[0].arguments["type"] == "routine"


def test_preprocess_detects_special_task():
    pets = [_make_pet("豆豆")]
    actions = pre_process("接下来一周每天给狗狗吃益生菌", pets, today=date(2026, 3, 28))
    task_actions = [a for a in actions if a.tool_name == "create_daily_task"]
    assert len(task_actions) >= 1
    assert task_actions[0].arguments["type"] == "special"


def test_preprocess_does_not_detect_task_for_question():
    pets = [_make_pet("豆豆")]
    actions = pre_process("每天要遛几次狗？", pets, today=date(2026, 3, 28))
    task_actions = [a for a in actions if a.tool_name == "create_daily_task"]
    assert len(task_actions) == 0
