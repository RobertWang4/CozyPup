"""Daily task tool handlers."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DailyTask, Pet, TaskType
from app.agents.tools.registry import register_tool
from app.agents.locale import t


@register_tool("create_daily_task")
async def create_daily_task(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Create a daily task for the user."""
    title = arguments["title"]
    daily_target = arguments.get("daily_target", 1)
    pet_id_str = arguments.get("pet_id")
    start_date_str = arguments.get("start_date") or date.today().isoformat()
    end_date_str = arguments.get("end_date")

    # Auto-determine type: has end_date → special, otherwise → routine
    task_type = TaskType.special if end_date_str else TaskType.routine

    pet = None
    if pet_id_str:
        pet_id = uuid.UUID(pet_id_str)
        pet_result = await db.execute(
            select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
        )
        pet = pet_result.scalar_one_or_none()
        if not pet:
            return {"success": False, "error": "Pet not found or does not belong to you"}
    else:
        pet_id = None

    task = DailyTask(
        id=uuid.uuid4(),
        user_id=user_id,
        pet_id=pet_id,
        title=title,
        type=task_type,
        daily_target=daily_target,
        start_date=date.fromisoformat(start_date_str),
        end_date=date.fromisoformat(end_date_str) if end_date_str else None,
        active=True,
    )
    db.add(task)
    await db.flush()

    card = {
        "type": "daily_task_created",
        "task_id": str(task.id),
        "title": title,
        "task_type": task_type.value,
        "daily_target": daily_target,
        "pet_name": pet.name if pet else None,
        "start_date": start_date_str,
        "end_date": end_date_str,
    }

    return {
        "success": True,
        "task_id": str(task.id),
        "title": title,
        "type": task_type.value,
        "daily_target": daily_target,
        "card": card,
    }


@register_tool("list_daily_tasks")
async def list_daily_tasks(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """List the user's active daily tasks."""
    result = await db.execute(
        select(DailyTask)
        .where(
            DailyTask.user_id == user_id,
            DailyTask.active == True,  # noqa: E712
        )
        .order_by(DailyTask.created_at)
    )
    tasks = result.scalars().all()

    return {
        "tasks": [
            {
                "task_id": str(t.id),
                "pet_id": str(t.pet_id) if t.pet_id else None,
                "title": t.title,
                "type": t.type.value,
                "daily_target": t.daily_target,
                "start_date": t.start_date.isoformat() if t.start_date else None,
                "end_date": t.end_date.isoformat() if t.end_date else None,
            }
            for t in tasks
        ],
        "count": len(tasks),
    }


@register_tool("manage_daily_task", accepts_kwargs=True)
async def manage_daily_task(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    **kwargs,
) -> dict:
    """Update, delete, or deactivate a daily task."""
    lang = kwargs.get("lang", "zh")
    action = arguments["action"]

    # Handle "delete_all" — bulk delete all active tasks for this user
    if action == "delete_all":
        result = await db.execute(
            select(DailyTask).where(
                DailyTask.user_id == user_id,
                DailyTask.active == True,  # noqa: E712
            )
        )
        tasks = result.scalars().all()
        if not tasks:
            no_tasks_msg = "没有待办需要删除" if lang == "zh" else "No tasks to delete"
            return {"success": True, "action": "delete_all", "deleted_count": 0, "message": "No active tasks to delete",
                    "card": {"type": "daily_task_deleted", "title": no_tasks_msg}}
        deleted_titles = [t.title for t in tasks]
        for t in tasks:
            await db.delete(t)
        await db.flush()
        n = len(deleted_titles)
        bulk_title = f"已删除 {n} 个待办" if lang == "zh" else f"Deleted {n} task(s)"
        return {
            "success": True,
            "action": "delete_all",
            "deleted_count": n,
            "deleted_titles": deleted_titles,
            "card": {
                "type": "daily_task_deleted",
                "title": bulk_title,
            },
        }

    task_id_str = arguments.get("task_id")
    title_keyword = arguments.get("title")

    # Fallback: "delete" without task_id/title → treat as "delete_all"
    if action == "delete" and not task_id_str and not title_keyword:
        action = "delete_all"
        result = await db.execute(
            select(DailyTask).where(
                DailyTask.user_id == user_id,
                DailyTask.active == True,  # noqa: E712
            )
        )
        tasks = result.scalars().all()
        if not tasks:
            no_tasks_msg = "没有待办需要删除" if lang == "zh" else "No tasks to delete"
            return {"success": True, "action": "delete_all", "deleted_count": 0, "message": "No active tasks to delete",
                    "card": {"type": "daily_task_deleted", "title": no_tasks_msg}}
        deleted_titles = [t.title for t in tasks]
        for t in tasks:
            await db.delete(t)
        await db.flush()
        n = len(deleted_titles)
        bulk_title = f"已删除 {n} 个待办" if lang == "zh" else f"Deleted {n} task(s)"
        return {
            "success": True,
            "action": "delete_all",
            "deleted_count": n,
            "deleted_titles": deleted_titles,
            "card": {
                "type": "daily_task_deleted",
                "title": bulk_title,
            },
        }

    task = None

    if task_id_str:
        task_id = uuid.UUID(task_id_str)
        result = await db.execute(
            select(DailyTask).where(
                DailyTask.id == task_id,
                DailyTask.user_id == user_id,
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            return {"success": False, "error": "Task not found or does not belong to you"}
    elif title_keyword:
        result = await db.execute(
            select(DailyTask).where(
                DailyTask.user_id == user_id,
                DailyTask.active == True,  # noqa: E712
                DailyTask.title.ilike(f"%{title_keyword}%"),
            )
        )
        matches = result.scalars().all()
        if not matches:
            return {"success": False, "error": f"No active task found matching '{title_keyword}'"}
        if len(matches) > 1:
            return {
                "success": False,
                "error": "Multiple tasks matched. Please specify task_id.",
                "matches": [
                    {"task_id": str(t.id), "title": t.title, "type": t.type.value}
                    for t in matches
                ],
            }
        task = matches[0]
    else:
        return {"success": False, "error": "Either task_id or title is required to identify the task"}

    original_title = task.title

    if action == "delete":
        await db.delete(task)
        await db.flush()
        return {
            "success": True,
            "action": "deleted",
            "task_id": str(task.id),
            "title": original_title,
            "card": {
                "type": "daily_task_deleted",
                "title": original_title,
            },
        }

    if action == "deactivate":
        task.active = False
        await db.flush()
        return {
            "success": True,
            "action": "deactivated",
            "task_id": str(task.id),
            "title": task.title,
            "card": {
                "type": "daily_task_updated",
                "task_id": str(task.id),
                "title": task.title,
                "active": False,
            },
        }

    if action == "update":
        updates = arguments.get("updates", {})
        if "title" in updates:
            task.title = updates["title"]
        if "daily_target" in updates:
            task.daily_target = updates["daily_target"]
        if "end_date" in updates:
            task.end_date = date.fromisoformat(updates["end_date"]) if updates["end_date"] else None
        await db.flush()
        return {
            "success": True,
            "action": "updated",
            "task_id": str(task.id),
            "title": task.title,
            "card": {
                "type": "daily_task_updated",
                "task_id": str(task.id),
                "title": task.title,
                "daily_target": task.daily_target,
            },
        }

    return {"success": False, "error": f"Unknown action: {action}"}
