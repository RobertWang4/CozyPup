import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.storage import upload_user_avatar as gcs_upload_user_avatar
from app.auth import (
    create_access_token,
    create_refresh_token,
    get_current_user_id,
    verify_apple_token,
    verify_google_token,
    verify_token,
)
from app.database import get_db
from app.models import User, FamilyInvite, Pet, PetCoOwner
from pydantic import BaseModel

from app.schemas.auth import (
    AuthRequest,
    AuthResponse,
    DevAuthRequest,
    RefreshRequest,
    RefreshResponse,
    UserResponse,
)


class UpdateUserRequest(BaseModel):
    name: str | None = None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


async def _find_or_create_user(
    db: AsyncSession, email: str, name: str | None, provider: str,
    avatar_url: str | None = None,
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=uuid.uuid4(),
            email=email,
            name=name,
            auth_provider=provider,
            avatar_url=avatar_url or "",
            subscription_status="trial",
            trial_start_date=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("user_created", extra={"user_id": str(user.id), "provider": provider})
    else:
        # Update avatar on every login (Google may change profile photo)
        if avatar_url and avatar_url != user.avatar_url:
            user.avatar_url = avatar_url
            await db.commit()
        logger.info("user_login", extra={"user_id": str(user.id), "provider": provider})

    return user


def _make_tokens(user: User) -> AuthResponse:
    user_id = str(user.id)
    return AuthResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        user_id=user_id,
        email=user.email,
        name=user.name,
        auth_provider=user.auth_provider,
        avatar_url=user.avatar_url or None,
    )


@router.post("/dev", response_model=AuthResponse)
async def login_dev(req: DevAuthRequest, db: AsyncSession = Depends(get_db)):
    """Dev-only login — no OAuth verification, just creates/finds user and returns tokens."""
    user = await _find_or_create_user(db, req.email, req.name, "dev")
    return _make_tokens(user)


@router.post("/apple", response_model=AuthResponse)
async def login_apple(req: AuthRequest, db: AsyncSession = Depends(get_db)):
    info = await verify_apple_token(req.id_token)
    user = await _find_or_create_user(db, info["email"], info.get("name"), "apple")
    return _make_tokens(user)


@router.post("/google", response_model=AuthResponse)
async def login_google(req: AuthRequest, db: AsyncSession = Depends(get_db)):
    info = await verify_google_token(req.id_token)
    user = await _find_or_create_user(db, info["email"], info.get("name"), "google", avatar_url=info.get("picture"))
    return _make_tokens(user)


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(req: RefreshRequest):
    payload = verify_token(req.refresh_token, "refresh")
    new_access = create_access_token(payload["sub"])
    return RefreshResponse(access_token=new_access)


@router.get("/me", response_model=UserResponse)
async def me(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url or None,
        auth_provider=user.auth_provider,
        phone_number=user.phone_number,
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    req: UpdateUserRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if req.name is not None:
        user.name = req.name.strip()
    await db.commit()
    await db.refresh(user)
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url or None,
        auth_provider=user.auth_provider,
        phone_number=user.phone_number,
    )


@router.delete("/me")
async def delete_account(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete user account and all associated data.

    Handles:
    - Duo Plan: if payer, convert member to independent subscription
    - Shared pets: if owner, transfer to co-owner; if co-owner, just remove
    - Cascade deletes: sessions, chats, reminders, events, device tokens
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # --- Handle Duo Plan ---
    if user.family_role == "payer":
        # Find the member and convert to independent subscription
        member_q = await db.execute(
            select(User).where(User.family_payer_id == user_id)
        )
        member = member_q.scalar_one_or_none()
        if member:
            member.family_role = None
            member.family_payer_id = None
            logger.info("duo_dissolved_on_delete", extra={
                "payer_id": str(user_id),
                "member_id": str(member.id),
            })
        # Cancel pending invites
        pending_q = await db.execute(
            select(FamilyInvite).where(
                FamilyInvite.inviter_id == user_id,
                FamilyInvite.status == "pending",
            )
        )
        for invite in pending_q.scalars().all():
            invite.status = "revoked"

    elif user.family_role == "member":
        user.family_role = None
        user.family_payer_id = None

    # --- Handle shared pets ---
    owned_pets_q = await db.execute(
        select(Pet).where(Pet.user_id == user_id)
    )
    for pet in owned_pets_q.scalars().all():
        co_owner_q = await db.execute(
            select(PetCoOwner).where(PetCoOwner.pet_id == pet.id)
        )
        co_owner = co_owner_q.scalars().first()
        if co_owner:
            # Transfer ownership to first co-owner
            pet.user_id = co_owner.user_id
            await db.execute(
                PetCoOwner.__table__.delete().where(
                    PetCoOwner.pet_id == pet.id,
                    PetCoOwner.user_id == co_owner.user_id,
                )
            )
            logger.info("pet_transferred_on_delete", extra={
                "pet_id": str(pet.id),
                "from": str(user_id),
                "to": str(co_owner.user_id),
            })

    # Remove co-owner entries where this user is a co-owner
    await db.execute(
        PetCoOwner.__table__.delete().where(PetCoOwner.user_id == user_id)
    )

    # --- Delete user (cascade deletes everything else) ---
    await db.delete(user)
    await db.commit()

    logger.info("account_deleted", extra={"user_id": str(user_id)})
    return {"status": "deleted"}


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Upload the current user's profile avatar."""
    if file.content_type not in ("image/jpeg", "image/png", "image/heic", "image/webp"):
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, HEIC, or WebP images are allowed")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if settings.gcs_bucket:
        url = gcs_upload_user_avatar(str(user_id), content, file.content_type)
    else:
        from pathlib import Path
        upload_dir = Path(__file__).resolve().parent.parent / "uploads" / "users"
        upload_dir.mkdir(parents=True, exist_ok=True)
        ext = file.content_type.split("/")[-1].replace("jpeg", "jpg")
        filepath = upload_dir / f"{user_id}.{ext}"
        filepath.write_bytes(content)
        url = f"/api/v1/auth/me/avatar/file"  # not served; dev only

    user.avatar_url = url
    await db.commit()
    await db.refresh(user)

    logger.info("user_avatar_uploaded", extra={"user_id": str(user_id)})
    return {"avatar_url": url}
