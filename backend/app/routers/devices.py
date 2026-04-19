"""Device token registration for APNs push notifications.

Mount: /api/v1/devices. The iOS client posts its APNs token on launch and after
renewal. The push sender (Phase 4) joins DeviceToken on user_id to fan out
notifications for reminders and family/pet-share events.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.models import DeviceToken

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


class DeviceRegisterRequest(BaseModel):
    token: str
    platform: str = "ios"


class DeviceResponse(BaseModel):
    id: str
    token: str
    platform: str


@router.post("", response_model=DeviceResponse, status_code=201)
async def register_device(
    req: DeviceRegisterRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Register (or re-bind) an APNs token to the caller.

    Upsert by token string: a device may change accounts (sign-out / sign-in),
    so the same token string is reattached to the latest caller rather than
    erroring on the unique constraint.
    """
    # Upsert: if token exists, update user_id
    result = await db.execute(
        select(DeviceToken).where(DeviceToken.token == req.token)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.user_id = user_id
        existing.platform = req.platform
        await db.commit()
        await db.refresh(existing)
        device = existing
    else:
        device = DeviceToken(
            id=uuid.uuid4(),
            user_id=user_id,
            token=req.token,
            platform=req.platform,
        )
        db.add(device)
        await db.commit()
        await db.refresh(device)

    return DeviceResponse(id=str(device.id), token=device.token, platform=device.platform)


@router.delete("/{token}", status_code=204)
async def unregister_device(
    token: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Unregister a device token. Must belong to the caller."""
    result = await db.execute(
        select(DeviceToken).where(DeviceToken.token == token, DeviceToken.user_id == user_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await db.delete(device)
    await db.commit()
