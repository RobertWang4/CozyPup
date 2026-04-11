import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.models import (
    Pet, PetCoOwner, PetShareToken,
    CalendarEvent, Reminder,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/pets", tags=["pet-sharing"])

TOKEN_TTL_MINUTES = 10


class ShareTokenResponse(BaseModel):
    token: str
    expires_at: str


class AcceptShareRequest(BaseModel):
    token: str
    merge_pet_id: str | None = None


class UnshareRequest(BaseModel):
    keep_copy: bool = False


@router.post("/{pet_id}/share-token", response_model=ShareTokenResponse)
async def create_share_token(
    pet_id: str,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Generate a QR share token for a pet. Owner only."""
    pid = uuid.UUID(pet_id)
    pet_q = await db.execute(
        select(Pet).where(Pet.id == pid, Pet.user_id == user_id)
    )
    pet = pet_q.scalar_one_or_none()
    if not pet:
        raise HTTPException(404, detail="Pet not found or not owner")

    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)

    share_token = PetShareToken(
        pet_id=pid,
        owner_id=user_id,
        token=token,
        expires_at=expires,
    )
    db.add(share_token)
    await db.commit()

    return ShareTokenResponse(token=token, expires_at=expires.isoformat())


@router.post("/accept-share")
async def accept_share(
    req: AcceptShareRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Accept a pet share. Optionally merge with an existing pet."""
    token_q = await db.execute(
        select(PetShareToken).where(
            PetShareToken.token == req.token,
            PetShareToken.used == False,
        )
    )
    share_token = token_q.scalar_one_or_none()
    if not share_token:
        raise HTTPException(404, detail="Invalid or used share token")

    if datetime.now(timezone.utc) > share_token.expires_at:
        raise HTTPException(410, detail="Share token expired")

    if share_token.owner_id == user_id:
        raise HTTPException(400, detail="Cannot share with yourself")

    existing = await db.execute(
        select(PetCoOwner).where(
            PetCoOwner.pet_id == share_token.pet_id,
            PetCoOwner.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, detail="Already sharing this pet")

    share_token.used = True

    co_owner = PetCoOwner(
        pet_id=share_token.pet_id,
        user_id=user_id,
    )
    db.add(co_owner)

    if req.merge_pet_id:
        await _merge_pets(db, share_token.pet_id, uuid.UUID(req.merge_pet_id), user_id)

    await db.commit()

    logger.info("pet_share_accepted", extra={
        "pet_id": str(share_token.pet_id),
        "owner_id": str(share_token.owner_id),
        "co_owner_id": str(user_id),
        "merged": bool(req.merge_pet_id),
    })

    return {"status": "shared", "pet_id": str(share_token.pet_id)}


@router.post("/{pet_id}/unshare")
async def unshare_pet(
    pet_id: str,
    req: UnshareRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Co-owner leaves a shared pet. Optionally keep a copy."""
    pid = uuid.UUID(pet_id)

    co_q = await db.execute(
        select(PetCoOwner).where(
            PetCoOwner.pet_id == pid,
            PetCoOwner.user_id == user_id,
        )
    )
    co_owner = co_q.scalar_one_or_none()
    if not co_owner:
        raise HTTPException(404, detail="Not a co-owner of this pet")

    if req.keep_copy:
        await _deep_copy_pet(db, pid, user_id)

    await db.delete(co_owner)
    await db.commit()

    logger.info("pet_unshared", extra={
        "pet_id": pet_id,
        "user_id": str(user_id),
        "kept_copy": req.keep_copy,
    })

    return {"status": "unshared", "kept_copy": req.keep_copy}


async def _merge_pets(
    db: AsyncSession,
    target_pet_id: uuid.UUID,
    source_pet_id: uuid.UUID,
    source_user_id: uuid.UUID,
):
    """Merge source pet (B's) into target pet (A's). Moves events/reminders, deletes source."""
    source_q = await db.execute(
        select(Pet).where(Pet.id == source_pet_id, Pet.user_id == source_user_id)
    )
    source_pet = source_q.scalar_one_or_none()
    if not source_pet:
        return

    target_q = await db.execute(select(Pet).where(Pet.id == target_pet_id))
    target_pet = target_q.scalar_one_or_none()
    if not target_pet:
        return

    # Move calendar events
    await db.execute(
        update(CalendarEvent)
        .where(CalendarEvent.pet_id == source_pet_id)
        .values(pet_id=target_pet_id, created_by=source_user_id)
    )

    # Move reminders
    await db.execute(
        update(Reminder)
        .where(Reminder.pet_id == source_pet_id)
        .values(pet_id=target_pet_id, created_by=source_user_id)
    )

    # LLM merge profile_md
    if source_pet.profile_md or target_pet.profile_md:
        from app.agents.tools.profile_merge import merge_pet_profiles
        target_pet.profile_md = await merge_pet_profiles(
            target_pet.profile_md, source_pet.profile_md
        )

    # Delete source pet
    await db.delete(source_pet)

    logger.info("pet_merged", extra={
        "target": str(target_pet_id),
        "source": str(source_pet_id),
    })


async def _deep_copy_pet(
    db: AsyncSession, pet_id: uuid.UUID, user_id: uuid.UUID
):
    """Deep copy a pet and its data for the leaving co-owner."""
    pet_q = await db.execute(select(Pet).where(Pet.id == pet_id))
    original = pet_q.scalar_one_or_none()
    if not original:
        return

    new_pet = Pet(
        user_id=user_id,
        name=original.name,
        species=original.species,
        species_locked=original.species_locked,
        breed=original.breed,
        birthday=original.birthday,
        weight=original.weight,
        avatar_url=original.avatar_url,
        color_hex=original.color_hex,
        profile=original.profile,
        profile_md=original.profile_md,
    )
    db.add(new_pet)
    await db.flush()

    # Copy events
    events_q = await db.execute(
        select(CalendarEvent).where(CalendarEvent.pet_id == pet_id)
    )
    for event in events_q.scalars():
        new_event = CalendarEvent(
            user_id=user_id,
            pet_id=new_pet.id,
            title=event.title,
            category=event.category,
            event_date=event.event_date,
            notes=getattr(event, 'notes', None),
            raw_text=event.raw_text,
            source=event.source,
            cost=event.cost,
            created_by=event.created_by,
        )
        db.add(new_event)

    # Copy reminders
    reminders_q = await db.execute(
        select(Reminder).where(Reminder.pet_id == pet_id)
    )
    for rem in reminders_q.scalars():
        new_rem = Reminder(
            user_id=user_id,
            pet_id=new_pet.id,
            title=rem.title,
            body=rem.body,
            type=rem.type,
            trigger_at=rem.trigger_at,
            created_by=rem.created_by,
        )
        db.add(new_rem)

    logger.info("pet_deep_copied", extra={
        "original_id": str(pet_id),
        "copy_id": str(new_pet.id),
        "user_id": str(user_id),
    })
