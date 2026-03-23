import logging
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.models import Pet
from app.schemas.pets import PetCreate, PetResponse, PetUpdate

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads" / "avatars"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/pets", tags=["pets"])

PET_COLORS = ["E8835C", "6BA3BE", "7BAE7F", "9B7ED8", "E8A33C"]


def _pet_to_response(pet: Pet) -> PetResponse:
    return PetResponse(
        id=str(pet.id),
        name=pet.name,
        species=pet.species,
        breed=pet.breed,
        birthday=pet.birthday.isoformat() if pet.birthday else None,
        weight=pet.weight,
        avatar_url=pet.avatar_url,
        color_hex=pet.color_hex,
        created_at=pet.created_at.isoformat(),
    )


@router.post("", response_model=PetResponse, status_code=201)
async def create_pet(
    req: PetCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # Auto-assign color based on count of existing pets
    count_result = await db.execute(
        select(func.count()).where(Pet.user_id == user_id)
    )
    count = count_result.scalar() or 0
    color = PET_COLORS[count % len(PET_COLORS)]

    pet = Pet(
        id=uuid.uuid4(),
        user_id=user_id,
        name=req.name,
        species=req.species,
        breed=req.breed,
        birthday=date.fromisoformat(req.birthday) if req.birthday else None,
        weight=req.weight,
        color_hex=color,
    )
    db.add(pet)
    await db.commit()
    await db.refresh(pet)
    logger.info("pet_created", extra={"pet_id": str(pet.id), "pet_name": pet.name, "species": pet.species.value})
    return _pet_to_response(pet)


@router.get("", response_model=list[PetResponse])
async def list_pets(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Pet).where(Pet.user_id == user_id).order_by(Pet.created_at)
    )
    return [_pet_to_response(p) for p in result.scalars().all()]


@router.get("/{pet_id}", response_model=PetResponse)
async def get_pet(
    pet_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")
    return _pet_to_response(pet)


@router.put("/{pet_id}", response_model=PetResponse)
async def update_pet(
    pet_id: uuid.UUID,
    req: PetUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")

    if req.name is not None:
        pet.name = req.name
    if req.species is not None:
        pet.species = req.species
    if req.breed is not None:
        pet.breed = req.breed
    if req.birthday is not None:
        pet.birthday = date.fromisoformat(req.birthday)
    if req.weight is not None:
        pet.weight = req.weight

    await db.commit()
    await db.refresh(pet)
    logger.info("pet_updated", extra={"pet_id": str(pet.id)})
    return _pet_to_response(pet)


@router.delete("/{pet_id}", status_code=204)
async def delete_pet(
    pet_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")

    logger.info("pet_deleted", extra={"pet_id": str(pet.id), "pet_name": pet.name})
    await db.delete(pet)
    await db.commit()


@router.post("/{pet_id}/avatar", response_model=PetResponse)
async def upload_avatar(
    pet_id: uuid.UUID,
    file: UploadFile = File(...),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")

    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are allowed")

    ext = file.content_type.split("/")[-1].replace("jpeg", "jpg")
    filename = f"{pet_id}.{ext}"
    filepath = UPLOAD_DIR / filename

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")

    filepath.write_bytes(content)

    pet.avatar_url = f"/api/v1/pets/{pet_id}/avatar"
    await db.commit()
    await db.refresh(pet)
    logger.info("avatar_uploaded", extra={"pet_id": str(pet.id)})
    return _pet_to_response(pet)


@router.get("/{pet_id}/avatar")
async def get_avatar(pet_id: uuid.UUID):
    """Serve pet avatar image (public, no auth required)."""
    for ext in ("jpg", "png", "webp"):
        filepath = UPLOAD_DIR / f"{pet_id}.{ext}"
        if filepath.exists():
            media_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
            return FileResponse(filepath, media_type=media_type)

    raise HTTPException(status_code=404, detail="No avatar uploaded")
