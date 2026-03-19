import logging
import uuid
from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth import get_current_user_id
from app.database import get_db
from app.models import CalendarEvent, Pet
from app.schemas.calendar import (
    CalendarEventCreate,
    CalendarEventResponse,
    CalendarEventUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])


def _event_to_response(event: CalendarEvent) -> CalendarEventResponse:
    return CalendarEventResponse(
        id=str(event.id),
        pet_id=str(event.pet_id),
        pet_name=event.pet.name,
        pet_color_hex=event.pet.color_hex,
        event_date=event.event_date.isoformat(),
        event_time=event.event_time.strftime("%H:%M") if event.event_time else None,
        title=event.title,
        type=event.type,
        category=event.category,
        raw_text=event.raw_text,
        source=event.source,
        edited=event.edited,
        created_at=event.created_at.isoformat(),
    )


@router.post("", response_model=CalendarEventResponse, status_code=201)
async def create_event(
    req: CalendarEventCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # Verify pet belongs to user
    pet_result = await db.execute(
        select(Pet).where(Pet.id == uuid.UUID(req.pet_id), Pet.user_id == user_id)
    )
    if not pet_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Pet not found")

    event = CalendarEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        pet_id=uuid.UUID(req.pet_id),
        event_date=date.fromisoformat(req.event_date),
        event_time=time.fromisoformat(req.event_time) if req.event_time else None,
        title=req.title,
        type=req.type,
        category=req.category,
        raw_text=req.raw_text,
        source=req.source,
    )
    db.add(event)
    await db.commit()

    # Reload with pet relationship
    result = await db.execute(
        select(CalendarEvent)
        .options(joinedload(CalendarEvent.pet))
        .where(CalendarEvent.id == event.id)
    )
    event = result.scalar_one()
    return _event_to_response(event)


@router.get("", response_model=list[CalendarEventResponse])
async def list_events(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    pet_id: str | None = Query(None),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CalendarEvent)
        .options(joinedload(CalendarEvent.pet))
        .where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.event_date >= date.fromisoformat(start_date),
            CalendarEvent.event_date <= date.fromisoformat(end_date),
        )
        .order_by(CalendarEvent.event_date, CalendarEvent.event_time)
    )
    if pet_id:
        stmt = stmt.where(CalendarEvent.pet_id == uuid.UUID(pet_id))

    result = await db.execute(stmt)
    return [_event_to_response(e) for e in result.scalars().unique().all()]


@router.get("/{event_id}", response_model=CalendarEventResponse)
async def get_event(
    event_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CalendarEvent)
        .options(joinedload(CalendarEvent.pet))
        .where(CalendarEvent.id == event_id, CalendarEvent.user_id == user_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_to_response(event)


@router.put("/{event_id}", response_model=CalendarEventResponse)
async def update_event(
    event_id: uuid.UUID,
    req: CalendarEventUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CalendarEvent)
        .options(joinedload(CalendarEvent.pet))
        .where(CalendarEvent.id == event_id, CalendarEvent.user_id == user_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if req.title is not None:
        event.title = req.title
    if req.category is not None:
        event.category = req.category
    if req.event_date is not None:
        event.event_date = date.fromisoformat(req.event_date)
    if req.event_time is not None:
        event.event_time = time.fromisoformat(req.event_time)

    event.edited = True
    await db.commit()
    await db.refresh(event)
    return _event_to_response(event)


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id, CalendarEvent.user_id == user_id
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    await db.delete(event)
    await db.commit()
