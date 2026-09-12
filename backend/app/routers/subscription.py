import logging
from datetime import datetime, timedelta, timezone

from appstoreserverlibrary.signed_data_verifier import VerificationException
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.config import settings
from app.database import get_db
from app.middleware.subscription import billing_enabled
from app.models import AppleTransaction, User, Chat, CalendarEvent, Reminder
from app.schemas.subscription import (
    SubscriptionStatusResponse,
    TrialStatsResponse,
    VerifyRequest,
    VerifyResponse,
)
from app.storekit import verify_notification, verify_signed_transaction

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

    if not billing_enabled():
        # Free mode: everyone is a full (duo) member.
        return SubscriptionStatusResponse(
            status="active",
            trial_days_left=None,
            expires_at=None,
            product_id=user.subscription_product_id,
            is_duo=True,
        )

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
    """Verify a StoreKit 2 signedTransaction JWS and activate subscription.

    The client sends the raw JWS from StoreKit 2 VerificationResult. We verify
    the chain against Apple's root CAs and trust ONLY the decoded payload.
    The accepted StoreKit environment is decided server-side; `req.sandbox` is
    ignored (kept in the schema only so older clients don't 422).
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    try:
        # Verification does blocking work (cert chain + OCSP), so keep it off
        # the event loop.
        payload = await run_in_threadpool(
            verify_signed_transaction,
            req.signed_transaction,
            is_tester=bool(user.is_admin),
        )
    except VerificationException as exc:
        logger.warning("storekit_verify_failed", extra={
            "user_id": str(user_id),
            "reason": str(exc),
        })
        raise HTTPException(status_code=400, detail="invalid_signed_transaction") from exc

    if payload.bundleId != settings.apple_bundle_id:
        logger.warning("storekit_bundle_mismatch", extra={
            "expected": settings.apple_bundle_id,
            "got": payload.bundleId,
        })
        raise HTTPException(status_code=400, detail="bundle_mismatch")

    if payload.revocationDate is not None:
        raise HTTPException(status_code=400, detail="transaction_revoked")

    # Replay protection: an originalTransactionId belongs to exactly one
    # account, so a leaked/shared JWS can't activate a second one.
    original_id = str(payload.originalTransactionId or payload.transactionId or "")
    if not original_id:
        raise HTTPException(status_code=400, detail="missing_transaction_id")

    binding_q = await db.execute(
        select(AppleTransaction).where(
            AppleTransaction.original_transaction_id == original_id
        )
    )
    binding = binding_q.scalar_one_or_none()
    if binding is not None and binding.user_id != user_id:
        logger.warning("storekit_transaction_replay", extra={
            "user_id": str(user_id),
            "bound_user_id": str(binding.user_id),
            "original_transaction_id": original_id,
        })
        raise HTTPException(status_code=409, detail="transaction_already_bound")

    product_id = payload.productId
    expires_at = None
    if payload.expiresDate is not None:
        # expiresDate is ms since epoch per Apple spec
        expires_at = datetime.fromtimestamp(payload.expiresDate / 1000, tz=timezone.utc)

    environment = payload.environment.value if payload.environment else ""
    if binding is None:
        db.add(AppleTransaction(
            original_transaction_id=original_id,
            user_id=user_id,
            environment=environment,
            product_id=product_id,
            last_transaction_id=str(payload.transactionId or ""),
        ))
    else:
        binding.environment = environment
        binding.product_id = product_id
        binding.last_transaction_id = str(payload.transactionId or "")

    user.subscription_status = "active"
    user.subscription_product_id = product_id
    user.subscription_expires_at = expires_at

    # If downgrading from duo to individual, revoke partner
    if ".duo" not in product_id and user.family_role == "payer":
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
        "product_id": product_id,
        "transaction_id": str(payload.transactionId),
        "environment": payload.environment.value if payload.environment else None,
    })

    return VerifyResponse(
        status="active",
        expires_at=user.subscription_expires_at,
    )



# ---------------------------------------------------------------------------
# App Store Server Notifications V2
# ---------------------------------------------------------------------------

# Notification types that end access.
_EXPIRING_TYPES = {"EXPIRED", "REFUND", "REVOKE"}
# Notification types that (re)grant access.
_ACTIVATING_TYPES = {"SUBSCRIBED", "DID_RENEW"}


@router.post("/webhook")
async def appstore_webhook(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """App Store Server Notifications V2.

    Apple POSTs `{"signedPayload": "<JWS>"}`. We verify the JWS the same way
    as a client transaction (server-decided environment, Apple root CAs), find
    the owner via the originalTransactionId binding written by /verify, then
    move `subscription_status` / `subscription_expires_at`.

    Always 200 on a verified payload — Apple retries non-2xx, and an unknown
    or unroutable notification is not something a retry can fix.
    """
    signed_payload = body.get("signedPayload")
    if not isinstance(signed_payload, str) or not signed_payload:
        raise HTTPException(status_code=400, detail="missing_signed_payload")

    try:
        notification = await run_in_threadpool(verify_notification, signed_payload)
    except VerificationException as exc:
        logger.warning("appstore_webhook_verify_failed", extra={"reason": str(exc)})
        raise HTTPException(status_code=400, detail="invalid_signed_payload") from exc

    kind = str(notification.rawNotificationType or "")
    subtype = str(notification.rawSubtype or "")
    data = notification.data
    signed_tx = getattr(data, "signedTransactionInfo", None) if data else None
    if not signed_tx:
        logger.info("appstore_webhook_no_transaction", extra={"type": kind})
        return {"status": "ignored", "type": kind}

    try:
        tx = await run_in_threadpool(verify_signed_transaction, signed_tx)
    except VerificationException as exc:
        logger.warning("appstore_webhook_tx_verify_failed", extra={
            "type": kind,
            "reason": str(exc),
        })
        raise HTTPException(status_code=400, detail="invalid_transaction_info") from exc

    original_id = str(tx.originalTransactionId or tx.transactionId or "")
    binding_q = await db.execute(
        select(AppleTransaction).where(
            AppleTransaction.original_transaction_id == original_id
        )
    )
    binding = binding_q.scalar_one_or_none()
    if binding is None:
        # No account ever activated this subscription with us (e.g. a sandbox
        # tester, or a purchase that never reached /verify). Nothing to do.
        logger.info("appstore_webhook_unknown_transaction", extra={
            "type": kind,
            "original_transaction_id": original_id,
        })
        return {"status": "ignored", "type": kind}

    user_q = await db.execute(select(User).where(User.id == binding.user_id))
    user = user_q.scalar_one_or_none()
    if user is None:
        return {"status": "ignored", "type": kind}

    expires_at = None
    if tx.expiresDate is not None:
        expires_at = datetime.fromtimestamp(tx.expiresDate / 1000, tz=timezone.utc)

    applied = "ignored"
    if kind in _ACTIVATING_TYPES:
        user.subscription_status = "active"
        user.subscription_product_id = tx.productId
        user.subscription_expires_at = expires_at
        applied = "active"
    elif kind in _EXPIRING_TYPES:
        user.subscription_status = "expired"
        user.subscription_expires_at = expires_at
        applied = "expired"
    elif kind == "DID_FAIL_TO_RENEW":
        # In the billing-retry grace period the user still has access; Apple
        # sends EXPIRED later if it never recovers.
        if subtype != "GRACE_PERIOD":
            user.subscription_status = "expired"
            user.subscription_expires_at = expires_at
            applied = "expired"

    if applied != "ignored":
        binding.last_transaction_id = str(tx.transactionId or "")
        await db.commit()

    logger.info("appstore_webhook_handled", extra={
        "type": kind,
        "subtype": subtype,
        "user_id": str(user.id),
        "applied": applied,
    })
    return {"status": applied, "type": kind}
