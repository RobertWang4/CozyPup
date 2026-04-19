"""Daily task (habit tracker) routes.

Mount: /api/v1/tasks. Two task kinds: `routine` (every day) and `special`
(windowed by start_date/end_date, e.g. a medication course). Completions are
counted per (task, date) in DailyTaskCompletion, capped at task.daily_target.
Tap/untap endpoints drive the per-day progress UI on the home screen.
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.models import DailyTask, DailyTaskCompletion, Pet, TaskType
from app.schemas.tasks import (
    DailyTaskCreate,
    DailyTaskResponse,
    DailyTaskUpdate,
    TapResponse,
    TodayResponse,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


def _task_to_response(task: DailyTask, completed_count: int, pet: Pet | None) -> DailyTaskResponse:
    pet_dict = None
    if pet is not None:
        pet_dict = {"id": str(pet.id), "name": pet.name, "color_hex": pet.color_hex}
    return DailyTaskResponse(
        id=str(task.id),
        title=task.title,
        type=task.type.value,
        daily_target=task.daily_target,
        completed_count=completed_count,
        pet=pet_dict,
        active=task.active,
        start_date=task.start_date.isoformat() if task.start_date else None,
        end_date=task.end_date.isoformat() if task.end_date else None,
    )


async def _get_today_tasks(db: AsyncSession, user_id: uuid.UUID, today: date) -> dict:
    """Return {tasks, all_completed} for today.

    Combines routine tasks with any special task whose [start_date, end_date]
    window includes today, and LEFT-JOINs per-task completion counts so tasks
    without a completion row still show up with count=0.
    """
    # Subquery: today's completion counts per task
    comp_sub = (
        select(
            DailyTaskCompletion.task_id,
            DailyTaskCompletion.count,
        )
        .where(DailyTaskCompletion.date == today)
        .subquery()
    )

    # Main query with LEFT JOINs
    stmt = (
        select(DailyTask, func.coalesce(comp_sub.c.count, 0).label("completed_count"), Pet)
        .outerjoin(comp_sub, DailyTask.id == comp_sub.c.task_id)
        .outerjoin(Pet, DailyTask.pet_id == Pet.id)
        .where(
            DailyTask.user_id == user_id,
            DailyTask.active == True,
            (
                (DailyTask.type == TaskType.routine)
                | (
                    (DailyTask.type == TaskType.special)
                    & (DailyTask.start_date <= today)
                    & (DailyTask.end_date >= today)
                )
            ),
        )
        .order_by(DailyTask.created_at)
    )

    result = await db.execute(stmt)
    rows = result.all()

    tasks = [
        _task_to_response(task, completed_count, pet)
        for task, completed_count, pet in rows
    ]
    all_completed = all(t.completed_count >= t.daily_target for t in tasks) if tasks else True

    return {"tasks": tasks, "all_completed": all_completed}


@router.get("/today", response_model=TodayResponse)
async def get_today_tasks(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    data = await _get_today_tasks(db, user_id, today)
    return TodayResponse(**data)


@router.post("", response_model=DailyTaskResponse, status_code=201)
async def create_task(
    req: DailyTaskCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    pet = None
    if req.pet_id is not None:
        result = await db.execute(
            select(Pet).where(Pet.id == uuid.UUID(req.pet_id), Pet.user_id == user_id)
        )
        pet = result.scalar_one_or_none()
        if not pet:
            raise HTTPException(status_code=404, detail="Pet not found")

    task = DailyTask(
        id=uuid.uuid4(),
        user_id=user_id,
        pet_id=uuid.UUID(req.pet_id) if req.pet_id else None,
        title=req.title,
        type=TaskType(req.type),
        daily_target=req.daily_target,
        start_date=date.fromisoformat(req.start_date) if req.start_date else None,
        end_date=date.fromisoformat(req.end_date) if req.end_date else None,
        active=True,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    return _task_to_response(task, 0, pet)


@router.put("/{task_id}", response_model=DailyTaskResponse)
async def update_task(
    task_id: uuid.UUID,
    req: DailyTaskUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DailyTask).where(DailyTask.id == task_id, DailyTask.user_id == user_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if req.title is not None:
        task.title = req.title
    if req.daily_target is not None:
        task.daily_target = req.daily_target
    if req.start_date is not None:
        task.start_date = date.fromisoformat(req.start_date)
    if req.end_date is not None:
        task.end_date = date.fromisoformat(req.end_date)
    if req.active is not None:
        task.active = req.active

    await db.commit()
    await db.refresh(task)

    # Load pet if associated
    pet = None
    if task.pet_id:
        pet_result = await db.execute(select(Pet).where(Pet.id == task.pet_id))
        pet = pet_result.scalar_one_or_none()

    # Get today's completion count
    today = date.today()
    comp_result = await db.execute(
        select(DailyTaskCompletion).where(
            DailyTaskCompletion.task_id == task.id,
            DailyTaskCompletion.date == today,
        )
    )
    comp = comp_result.scalar_one_or_none()
    completed_count = comp.count if comp else 0

    return _task_to_response(task, completed_count, pet)


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DailyTask).where(DailyTask.id == task_id, DailyTask.user_id == user_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    await db.delete(task)
    await db.commit()
    return Response(status_code=204)


@router.post("/{task_id}/tap", response_model=TapResponse)
async def tap_task(
    task_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Increment today's completion count for a task (capped at daily_target)."""
    result = await db.execute(
        select(DailyTask).where(DailyTask.id == task_id, DailyTask.user_id == user_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    today = date.today()

    # Get or create today's completion record
    comp_result = await db.execute(
        select(DailyTaskCompletion).where(
            DailyTaskCompletion.task_id == task_id,
            DailyTaskCompletion.date == today,
        )
    )
    comp = comp_result.scalar_one_or_none()

    if comp is None:
        comp = DailyTaskCompletion(
            id=uuid.uuid4(),
            task_id=task_id,
            date=today,
            count=0,
        )
        db.add(comp)
        await db.flush()

    # Cap at daily_target so repeated taps after reaching the goal are no-ops.
    if comp.count < task.daily_target:
        comp.count += 1

    await db.commit()
    await db.refresh(comp)

    # Check all_completed for today's tasks
    data = await _get_today_tasks(db, user_id, today)

    return TapResponse(
        task_id=str(task_id),
        completed_count=comp.count,
        daily_target=task.daily_target,
        all_completed=data["all_completed"],
    )


@router.post("/{task_id}/untap", response_model=TapResponse)
async def untap_task(
    task_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Undo one completion tap for a task today."""
    result = await db.execute(
        select(DailyTask).where(DailyTask.id == task_id, DailyTask.user_id == user_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    today = date.today()

    comp_result = await db.execute(
        select(DailyTaskCompletion).where(
            DailyTaskCompletion.task_id == task_id,
            DailyTaskCompletion.date == today,
        )
    )
    comp = comp_result.scalar_one_or_none()

    if comp is not None and comp.count > 0:
        comp.count -= 1
        if comp.count == 0:
            await db.delete(comp)
        await db.commit()

    count = comp.count if comp is not None and comp.count > 0 else 0
    data = await _get_today_tasks(db, user_id, today)

    return TapResponse(
        task_id=str(task_id),
        completed_count=count,
        daily_target=task.daily_target,
        all_completed=data["all_completed"],
    )
