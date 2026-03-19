import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth import get_current_user_id
from app.database import get_db
from app.models import Pet, Reminder
from app.schemas.reminders import ReminderCreate, ReminderResponse, ReminderUpdate

router = APIRouter(prefix="/api/v1/reminders", tags=["reminders"])


def _reminder_to_response(r: Reminder) -> ReminderResponse:
    return ReminderResponse(
        id=str(r.id),
        pet_id=str(r.pet_id),
        pet_name=r.pet.name,
        type=r.type,
        title=r.title,
        body=r.body,
        trigger_at=r.trigger_at.isoformat(),
        sent=r.sent,
        created_at=r.created_at.isoformat(),
    )


@router.post("", response_model=ReminderResponse, status_code=201)
async def create_reminder(
    req: ReminderCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    pet_result = await db.execute(
        select(Pet).where(Pet.id == uuid.UUID(req.pet_id), Pet.user_id == user_id)
    )
    if not pet_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Pet not found")

    reminder = Reminder(
        id=uuid.uuid4(),
        user_id=user_id,
        pet_id=uuid.UUID(req.pet_id),
        type=req.type,
        title=req.title,
        body=req.body,
        trigger_at=datetime.fromisoformat(req.trigger_at),
    )
    db.add(reminder)
    await db.commit()

    result = await db.execute(
        select(Reminder).options(joinedload(Reminder.pet)).where(Reminder.id == reminder.id)
    )
    reminder = result.scalar_one()
    return _reminder_to_response(reminder)


@router.get("", response_model=list[ReminderResponse])
async def list_reminders(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reminder)
        .options(joinedload(Reminder.pet))
        .where(Reminder.user_id == user_id, Reminder.sent == False)
        .order_by(Reminder.trigger_at)
    )
    return [_reminder_to_response(r) for r in result.scalars().unique().all()]


@router.put("/{reminder_id}", response_model=ReminderResponse)
async def update_reminder(
    reminder_id: uuid.UUID,
    req: ReminderUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reminder)
        .options(joinedload(Reminder.pet))
        .where(Reminder.id == reminder_id, Reminder.user_id == user_id)
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    if req.title is not None:
        reminder.title = req.title
    if req.body is not None:
        reminder.body = req.body
    if req.trigger_at is not None:
        reminder.trigger_at = datetime.fromisoformat(req.trigger_at)

    await db.commit()
    await db.refresh(reminder)
    return _reminder_to_response(reminder)


@router.delete("/{reminder_id}", status_code=204)
async def delete_reminder(
    reminder_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user_id)
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    await db.delete(reminder)
    await db.commit()
