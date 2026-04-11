import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
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


def _is_duo_product(product_id: str | None) -> bool:
    return bool(product_id and ".duo" in product_id)


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
            select(FamilyInvite).where(
                FamilyInvite.inviter_id == user.id,
                FamilyInvite.status == "pending",
            )
        )
        pending = pending_q.scalar_one_or_none()
        if pending:
            resp.invite_pending = True
            resp.pending_invite_email = pending.invitee_email

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

    if req.email.lower() == user.email.lower():
        raise HTTPException(400, detail="Cannot invite yourself")

    # Revoke any existing pending invites
    old_invites = await db.execute(
        select(FamilyInvite).where(
            FamilyInvite.inviter_id == user.id,
            FamilyInvite.status == "pending",
        )
    )
    for old in old_invites.scalars():
        old.status = "revoked"

    invite = FamilyInvite(
        inviter_id=user.id,
        invitee_email=req.email.lower(),
    )
    db.add(invite)
    user.family_role = "payer"
    await db.commit()
    await db.refresh(invite)

    _send_invite_email(user.name or user.email, req.email, str(invite.id))

    logger.info("family_invite_sent", extra={
        "inviter_id": str(user.id),
        "invitee_email": req.email,
        "invite_id": str(invite.id),
    })

    return FamilyInviteResponse(
        invite_id=str(invite.id),
        status="pending",
        invitee_email=req.email,
    )


@router.post("/accept")
async def accept_invite(
    req: FamilyAcceptRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    invite_q = await db.execute(
        select(FamilyInvite).where(FamilyInvite.id == req.invite_id)
    )
    invite = invite_q.scalar_one_or_none()
    if not invite or invite.status != "pending":
        raise HTTPException(404, detail="Invite not found or already used")

    user_q = await db.execute(select(User).where(User.id == user_id))
    user = user_q.scalar_one()
    if user.email.lower() != invite.invitee_email.lower():
        raise HTTPException(403, detail="This invite is for a different email")

    if user.family_role == "member":
        raise HTTPException(400, detail="Already a member of another family")

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


def _send_invite_email(inviter_name: str, invitee_email: str, invite_id: str):
    """Send invite email. Placeholder — implement with SendGrid or SMTP."""
    logger.info("family_invite_email", extra={
        "to": invitee_email,
        "inviter": inviter_name,
        "invite_id": invite_id,
    })
