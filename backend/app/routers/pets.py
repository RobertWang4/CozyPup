import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.models import Pet
from app.schemas.pets import PetCreate, PetResponse, PetUpdate
from app.storage import upload_avatar as gcs_upload_avatar, get_avatar_url
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/pets", tags=["pets"])

PET_COLORS = ["E8835C", "6BA3BE", "7BAE7F", "9B7ED8", "E8A33C"]

SPECIES_ZH = {"dog": "狗", "cat": "猫", "other": "其他"}


def _generate_initial_profile(
    name: str, species: str, breed: str, birthday: date | None, weight: float | None,
) -> str:
    lines = [f"# {name}", "", "## 基本信息"]
    lines.append(f"- 类型：{SPECIES_ZH.get(species, species)}")
    if breed:
        lines.append(f"- 品种：{breed}")
    if birthday:
        lines.append(f"- 生日：{birthday.isoformat()}")
    if weight and weight > 0:
        lines.append(f"- 体重：{weight:.1f} kg")
    lines.extend(["", "## 性格", "", "## 健康", "", "## 日常"])
    return "\n".join(lines)


def _pet_to_response(pet: Pet, is_co_owned: bool = False) -> PetResponse:
    gender = (pet.profile or {}).get("gender") if pet.profile else None
    return PetResponse(
        id=str(pet.id),
        name=pet.name,
        species=pet.species,
        breed=pet.breed,
        birthday=pet.birthday.isoformat() if pet.birthday else None,
        weight=pet.weight,
        gender=gender,
        species_locked=pet.species_locked,
        avatar_url=pet.avatar_url,
        color_hex=pet.color_hex,
        profile_md=pet.profile_md,
        is_co_owned=is_co_owned,
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

    bday = date.fromisoformat(req.birthday) if req.birthday else None
    pet = Pet(
        id=uuid.uuid4(),
        user_id=user_id,
        name=req.name,
        species=req.species,
        breed=req.breed,
        birthday=bday,
        weight=req.weight,
        color_hex=color,
        profile_md=_generate_initial_profile(req.name, req.species.value, req.breed, bday, req.weight),
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
    from app.agents.tools.ownership import get_user_pets
    pets = await get_user_pets(db, user_id)
    # Mark pets that user co-owns (not the original owner)
    return [_pet_to_response(p, is_co_owned=(p.user_id != user_id)) for p in pets]


@router.get("/{pet_id}", response_model=PetResponse)
async def get_pet(
    pet_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    from app.agents.tools.ownership import can_access_pet
    pet = await can_access_pet(db, str(pet_id), user_id)
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
    if req.species is not None and req.species != pet.species:
        if pet.species_locked:
            raise HTTPException(status_code=400, detail="Species can only be changed once")
        pet.species = req.species
        pet.species_locked = True
    if req.breed is not None:
        pet.breed = req.breed
    if req.birthday is not None:
        pet.birthday = date.fromisoformat(req.birthday)
    if req.weight is not None:
        pet.weight = req.weight
    if req.profile_md is not None:
        pet.profile_md = req.profile_md
    if req.gender is not None:
        existing = pet.profile or {}
        if existing.get("gender_locked"):
            raise HTTPException(status_code=400, detail="Gender can only be set once")
        existing["gender"] = req.gender
        existing["gender_locked"] = True
        pet.profile = existing

    # Sync all structured fields into profile JSON so AI always sees latest data
    profile = pet.profile or {}
    if pet.name:
        profile["name"] = pet.name
    if pet.breed:
        profile["breed"] = pet.breed
    if pet.birthday:
        profile["birthday"] = pet.birthday.isoformat()
    if pet.weight:
        profile["weight_kg"] = pet.weight
    pet.profile = profile

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

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")

    if settings.gcs_bucket:
        gcs_upload_avatar(str(pet_id), content, file.content_type)
    else:
        # Local fallback for development without GCS
        from pathlib import Path
        upload_dir = Path(__file__).resolve().parent.parent / "uploads" / "avatars"
        upload_dir.mkdir(parents=True, exist_ok=True)
        ext = file.content_type.split("/")[-1].replace("jpeg", "jpg")
        filepath = upload_dir / f"{pet_id}.{ext}"
        filepath.write_bytes(content)

    # Always use relative URL — iOS avatarURL() builds the full URL from this
    pet.avatar_url = f"/api/v1/pets/{pet_id}/avatar"
    await db.commit()
    await db.refresh(pet)
    logger.info("avatar_uploaded", extra={"pet_id": str(pet.id)})
    return _pet_to_response(pet)


@router.get("/{pet_id}/avatar")
async def get_avatar(pet_id: uuid.UUID):
    """Serve pet avatar — redirect to GCS or serve local file."""
    if settings.gcs_bucket:
        from google.cloud import storage as gcs
        client = gcs.Client()
        bucket = client.bucket(settings.gcs_bucket)
        import time
        for ext in ("jpg", "png", "webp"):
            blob = bucket.blob(f"avatars/{pet_id}.{ext}")
            if blob.exists():
                base_url = get_avatar_url(f"avatars/{pet_id}.{ext}")
                return RedirectResponse(
                    url=f"{base_url}?v={int(time.time())}",
                    status_code=302,
                )
        raise HTTPException(status_code=404, detail="No avatar uploaded")
    else:
        # Local fallback
        from pathlib import Path
        from fastapi.responses import FileResponse
        upload_dir = Path(__file__).resolve().parent.parent / "uploads" / "avatars"
        for ext in ("jpg", "png", "webp"):
            filepath = upload_dir / f"{pet_id}.{ext}"
            if filepath.exists():
                media_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
                return FileResponse(filepath, media_type=media_type)
        raise HTTPException(status_code=404, detail="No avatar uploaded")
