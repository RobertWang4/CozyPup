import logging
import uuid
from datetime import date, time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.auth import get_current_user_id
from app.database import get_db
from app.models import CalendarEvent, Pet
from app.schemas.calendar import (
    CalendarEventCreate,
    CalendarEventResponse,
    CalendarEventUpdate,
    PetTag,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])

PHOTO_DIR = Path("/app/uploads/photos") if Path("/app/uploads").exists() else Path(__file__).resolve().parent.parent / "uploads" / "photos"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_PHOTOS = 4


def _event_to_response(event: CalendarEvent, pets_by_id: dict | None = None) -> CalendarEventResponse:
    """Convert a CalendarEvent to API response, resolving pet names."""
    pets_by_id = pets_by_id or {}

    # Build pet tags from pet_ids
    pet_tags: list[PetTag] = []
    pet_id_list = event.pet_ids or []
    if pet_id_list:
        for pid in pet_id_list:
            pet = pets_by_id.get(pid)
            if pet:
                pet_tags.append(PetTag(id=str(pet.id), name=pet.name, color_hex=pet.color_hex))
    elif event.pet_id:
        pet = pets_by_id.get(str(event.pet_id))
        if pet:
            pet_tags.append(PetTag(id=str(pet.id), name=pet.name, color_hex=pet.color_hex))

    # Backward compat: primary pet
    primary_pet = pets_by_id.get(str(event.pet_id)) if event.pet_id else None

    return CalendarEventResponse(
        id=str(event.id),
        pet_id=str(event.pet_id) if event.pet_id else None,
        pet_name=primary_pet.name if primary_pet else "",
        pet_color_hex=primary_pet.color_hex if primary_pet else "",
        pet_tags=pet_tags,
        event_date=event.event_date.isoformat(),
        event_time=event.event_time.strftime("%H:%M") if event.event_time else None,
        title=event.title,
        type=event.type,
        category=event.category,
        raw_text=event.raw_text,
        source=event.source,
        edited=event.edited,
        photos=event.photos or [],
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
    events = result.scalars().unique().all()

    # Load all user's pets for name resolution
    pets_result = await db.execute(select(Pet).where(Pet.user_id == user_id))
    pets_by_id = {str(p.id): p for p in pets_result.scalars().all()}

    return [_event_to_response(e, pets_by_id) for e in events]


@router.get("/photos/{filename}")
async def get_photo(filename: str):
    path = PHOTO_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Photo not found")
    ext = filename.rsplit(".", 1)[-1]
    media_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
    return FileResponse(path, media_type=media_type)


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


@router.post("/{event_id}/photos", response_model=CalendarEventResponse)
async def upload_event_photo(
    event_id: uuid.UUID,
    file: UploadFile = File(...),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # 1. Get event + verify ownership
    result = await db.execute(
        select(CalendarEvent)
        .options(joinedload(CalendarEvent.pet))
        .where(CalendarEvent.id == event_id, CalendarEvent.user_id == user_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # 2. Check photo count
    current_photos = event.photos or []
    if len(current_photos) >= MAX_PHOTOS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_PHOTOS} photos per event")

    # 3. Validate MIME type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are allowed")

    # 4. Read + validate size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")

    # 5. Save file
    ext = file.content_type.split("/")[-1].replace("jpeg", "jpg")
    filename = f"{uuid.uuid4()}.{ext}"
    (PHOTO_DIR / filename).write_bytes(content)

    # 6. Append URL to photos
    photo_url = f"/api/v1/calendar/photos/{filename}"
    current_photos.append(photo_url)
    event.photos = current_photos
    flag_modified(event, "photos")

    await db.commit()
    await db.refresh(event)
    return _event_to_response(event)


@router.delete("/{event_id}/photos", response_model=CalendarEventResponse)
async def delete_event_photo(
    event_id: uuid.UUID,
    photo_url: str = Query(...),
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

    current_photos = event.photos or []
    if photo_url not in current_photos:
        raise HTTPException(status_code=404, detail="Photo not found on event")

    current_photos.remove(photo_url)
    event.photos = current_photos
    flag_modified(event, "photos")

    # Delete file from disk
    filename = photo_url.split("/")[-1]
    filepath = PHOTO_DIR / filename
    if filepath.exists():
        filepath.unlink()

    await db.commit()
    await db.refresh(event)
    return _event_to_response(event)
