from pydantic import BaseModel


class FamilyInviteRequest(BaseModel):
    """Request body for POST /family/invite.

    Email is optional — the modern flow generates a QR + link and the
    invitee authenticates via the web landing page. Keeping `email` as an
    optional field allows future "send by email" flows without a schema
    change.
    """
    email: str | None = None


class FamilyInviteResponse(BaseModel):
    invite_id: str
    status: str
    invitee_email: str | None = None
    invite_url: str
    expires_at: str  # ISO 8601


class FamilyStatusResponse(BaseModel):
    role: str | None = None  # "payer" | "member" | null
    partner_email: str | None = None
    partner_name: str | None = None
    invite_pending: bool = False
    pending_invite_email: str | None = None
    pending_invite_id: str | None = None
    pending_invite_url: str | None = None
    pending_invite_expires_at: str | None = None


class FamilyAcceptRequest(BaseModel):
    invite_id: str
