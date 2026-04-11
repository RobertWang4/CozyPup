from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.models import User

TRIAL_DAYS = 7

EXEMPT_PREFIXES = ("/api/v1/auth", "/api/v1/subscription")


async def require_active_subscription(
    request: Request,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Dependency that blocks write operations for expired users."""
    if request.method == "GET":
        return

    for prefix in EXEMPT_PREFIXES:
        if request.url.path.startswith(prefix):
            return

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return

    if user.subscription_status == "trial" and user.trial_start_date:
        elapsed = datetime.now(timezone.utc) - user.trial_start_date
        if elapsed > timedelta(days=TRIAL_DAYS):
            user.subscription_status = "expired"
            await db.commit()

    if user.subscription_status == "active" and user.subscription_expires_at:
        if datetime.now(timezone.utc) > user.subscription_expires_at:
            user.subscription_status = "expired"
            await db.commit()

    if user.subscription_status == "expired":
        raise HTTPException(
            status_code=403,
            detail={"code": "subscription_expired", "message": "Subscription expired"},
        )
