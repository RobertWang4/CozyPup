import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.config import settings
from app.database import get_db
from app.models import User, FamilyInvite
from app.schemas.family import (
    FamilyInviteRequest,
    FamilyInviteResponse,
    FamilyStatusResponse,
    FamilyAcceptRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/family", tags=["family"])

# How long a pending invite stays valid. 1 hour is enough to share the link
# via QR / iMessage / email / WhatsApp and have the invitee accept it, but
# short enough that abandoned invites don't pile up.
INVITE_TTL = timedelta(hours=1)


def _is_duo_product(product_id: str | None) -> bool:
    return bool(product_id and ".duo" in product_id)


def _invite_url(invite_id: str) -> str:
    """Build the public landing URL for an invite."""
    base = settings.server_public_url.rstrip("/")
    return f"{base}/invite/{invite_id}"


def _invite_is_live(invite: FamilyInvite) -> bool:
    if invite.status != "pending":
        return False
    if invite.expires_at is None:
        return True
    return datetime.now(timezone.utc) < invite.expires_at


@router.get("/status", response_model=FamilyStatusResponse)
async def get_family_status(
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    resp = FamilyStatusResponse(role=user.family_role)

    if user.family_role == "payer":
        member_q = await db.execute(
            select(User).where(User.family_payer_id == user.id)
        )
        member = member_q.scalar_one_or_none()
        if member:
            resp.partner_email = member.email
            resp.partner_name = member.name

        pending_q = await db.execute(
            select(FamilyInvite)
            .where(
                FamilyInvite.inviter_id == user.id,
                FamilyInvite.status == "pending",
            )
            .order_by(FamilyInvite.created_at.desc())
        )
        pending = pending_q.scalars().first()
        if pending and _invite_is_live(pending):
            resp.invite_pending = True
            resp.pending_invite_email = pending.invitee_email
            resp.pending_invite_id = str(pending.id)
            resp.pending_invite_url = _invite_url(str(pending.id))
            if pending.expires_at:
                resp.pending_invite_expires_at = pending.expires_at.isoformat()

    elif user.family_role == "member" and user.family_payer_id:
        payer_q = await db.execute(
            select(User).where(User.id == user.family_payer_id)
        )
        payer = payer_q.scalar_one_or_none()
        if payer:
            resp.partner_email = payer.email
            resp.partner_name = payer.name

    return resp


@router.post("/invite", response_model=FamilyInviteResponse)
async def invite_partner(
    req: FamilyInviteRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a pending family invite and return a shareable link.

    The invitee accepts either by:
    - opening the landing page in any browser (web OAuth flow), or
    - scanning the QR via another CozyPup user's in-app scanner,
      which hits POST /family/accept directly.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    if not _is_duo_product(user.subscription_product_id):
        raise HTTPException(400, detail="Duo plan required to invite a partner")

    if user.family_role == "payer":
        existing = await db.execute(
            select(User).where(User.family_payer_id == user.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(400, detail="You already have a partner")

    # Revoke any existing pending invites — only one active invite at a time.
    old_invites = await db.execute(
        select(FamilyInvite).where(
            FamilyInvite.inviter_id == user.id,
            FamilyInvite.status == "pending",
        )
    )
    for old in old_invites.scalars():
        old.status = "revoked"

    expires_at = datetime.now(timezone.utc) + INVITE_TTL
    invite = FamilyInvite(
        inviter_id=user.id,
        invitee_email=(req.email.lower() if req.email else None),
        expires_at=expires_at,
    )
    db.add(invite)
    user.family_role = "payer"
    await db.commit()
    await db.refresh(invite)

    logger.info("family_invite_created", extra={
        "inviter_id": str(user.id),
        "invite_id": str(invite.id),
        "has_email": req.email is not None,
    })

    return FamilyInviteResponse(
        invite_id=str(invite.id),
        status="pending",
        invitee_email=invite.invitee_email,
        invite_url=_invite_url(str(invite.id)),
        expires_at=expires_at.isoformat(),
    )


@router.post("/accept")
async def accept_invite(
    req: FamilyAcceptRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Accept a family invite by id.

    Called from the iOS app after scanning a QR code. The web landing page
    has its own internal accept path (see routers/web_invite.py) that runs
    in the OAuth callback, without requiring a pre-existing JWT.
    """
    invite_q = await db.execute(
        select(FamilyInvite).where(FamilyInvite.id == req.invite_id)
    )
    invite = invite_q.scalar_one_or_none()
    if not invite:
        raise HTTPException(404, detail="Invite not found")
    if not _invite_is_live(invite):
        # Mark expired for cleanup visibility
        if invite.status == "pending" and invite.expires_at and datetime.now(timezone.utc) >= invite.expires_at:
            invite.status = "expired"
            await db.commit()
        raise HTTPException(410, detail="Invite expired or already used")

    user_q = await db.execute(select(User).where(User.id == user_id))
    user = user_q.scalar_one()

    if user.id == invite.inviter_id:
        raise HTTPException(400, detail="Cannot accept your own invite")

    if user.family_role == "member" and user.family_payer_id != invite.inviter_id:
        raise HTTPException(400, detail="Already a member of another family")
    if user.family_role == "payer":
        raise HTTPException(400, detail="You are already a payer in a family plan")

    invite.status = "accepted"
    invite.invitee_id = user.id
    invite.accepted_at = datetime.now(timezone.utc)

    user.family_role = "member"
    user.family_payer_id = invite.inviter_id
    user.subscription_status = "active"

    await db.commit()

    logger.info("family_invite_accepted", extra={
        "inviter_id": str(invite.inviter_id),
        "invitee_id": str(user.id),
        "invite_id": str(invite.id),
    })

    return {"status": "accepted"}


@router.post("/revoke")
async def revoke_partner(
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Payer removes their partner."""
    user_q = await db.execute(select(User).where(User.id == user_id))
    user = user_q.scalar_one()

    if user.family_role != "payer":
        raise HTTPException(400, detail="Only the payer can revoke")

    member_q = await db.execute(
        select(User).where(User.family_payer_id == user.id)
    )
    member = member_q.scalar_one_or_none()
    if member:
        member.family_role = None
        member.family_payer_id = None
        member.subscription_status = "expired"
        logger.info("family_member_revoked", extra={
            "payer_id": str(user.id),
            "member_id": str(member.id),
        })

    pending = await db.execute(
        select(FamilyInvite).where(
            FamilyInvite.inviter_id == user.id,
            FamilyInvite.status == "pending",
        )
    )
    for inv in pending.scalars():
        inv.status = "revoked"

    user.family_role = None
    await db.commit()

    return {"status": "revoked"}
