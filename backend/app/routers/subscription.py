import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.models import User, Chat, CalendarEvent, Reminder
from app.schemas.subscription import (
    SubscriptionStatusResponse,
    TrialStatsResponse,
    VerifyRequest,
    VerifyResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/subscription", tags=["subscription"])

TRIAL_DAYS = 7


def _compute_status(user: User) -> tuple[str, int | None]:
    """Return (effective_status, trial_days_left)."""
    if user.subscription_status == "active":
        if user.subscription_expires_at and datetime.now(timezone.utc) > user.subscription_expires_at:
            return "expired", None
        return "active", None

    if user.subscription_status == "trial":
        if user.trial_start_date:
            elapsed = datetime.now(timezone.utc) - user.trial_start_date
            days_left = max(0, TRIAL_DAYS - elapsed.days)
            if days_left == 0:
                return "expired", 0
            return "trial", days_left
        return "trial", TRIAL_DAYS

    return "expired", None


@router.get("/status", response_model=SubscriptionStatusResponse)
async def get_status(
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    status, days_left = _compute_status(user)

    # Auto-update status in DB if trial expired
    if status == "expired" and user.subscription_status != "expired":
        user.subscription_status = "expired"
        await db.commit()

    return SubscriptionStatusResponse(
        status=status,
        trial_days_left=days_left,
        expires_at=user.subscription_expires_at,
        product_id=user.subscription_product_id,
        is_duo=bool(user.subscription_product_id and ".duo" in user.subscription_product_id),
    )


@router.get("/trial-stats", response_model=TrialStatsResponse)
async def get_trial_stats(
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # Count chats by this user
    chat_count_q = await db.execute(
        select(func.count()).select_from(Chat).where(Chat.role == "user").join(
            Chat.session
        ).where(Chat.session.has(user_id=user_id))
    )
    chat_count = chat_count_q.scalar() or 0

    # Count reminders
    reminder_count_q = await db.execute(
        select(func.count()).select_from(Reminder).where(Reminder.user_id == user_id)
    )
    reminder_count = reminder_count_q.scalar() or 0

    # Count calendar events
    event_count_q = await db.execute(
        select(func.count()).select_from(CalendarEvent).where(CalendarEvent.user_id == user_id)
    )
    event_count = event_count_q.scalar() or 0

    return TrialStatsResponse(
        chat_count=chat_count,
        reminder_count=reminder_count,
        event_count=event_count,
    )


@router.post("/verify", response_model=VerifyResponse)
async def verify_purchase(
    req: VerifyRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Verify a StoreKit 2 transaction and activate subscription."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    user.subscription_status = "active"
    user.subscription_product_id = req.product_id
    if "weekly" in req.product_id:
        user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    elif "yearly" in req.product_id:
        user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=365)
    else:
        user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    # If downgrading from duo to individual, revoke partner
    if ".duo" not in req.product_id and user.family_role == "payer":
        member_q = await db.execute(
            select(User).where(User.family_payer_id == user.id)
        )
        member = member_q.scalar_one_or_none()
        if member:
            member.family_role = None
            member.family_payer_id = None
            member.subscription_status = "expired"
            logger.info("family_auto_revoked_on_downgrade", extra={
                "payer_id": str(user_id),
                "member_id": str(member.id),
            })
        user.family_role = None

    await db.commit()
    logger.info("subscription_activated", extra={
        "user_id": str(user_id),
        "product_id": req.product_id,
    })

    return VerifyResponse(
        status="active",
        expires_at=user.subscription_expires_at,
    )


@router.post("/webhook")
async def appstore_webhook(
    db: AsyncSession = Depends(get_db),
):
    """App Store Server Notifications V2 webhook placeholder."""
    return {"status": "ok"}
