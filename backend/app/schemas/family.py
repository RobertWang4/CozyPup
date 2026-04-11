from pydantic import BaseModel


class FamilyInviteRequest(BaseModel):
    email: str


class FamilyInviteResponse(BaseModel):
    invite_id: str
    status: str
    invitee_email: str


class FamilyStatusResponse(BaseModel):
    role: str | None = None  # "payer" | "member" | null
    partner_email: str | None = None
    partner_name: str | None = None
    invite_pending: bool = False
    pending_invite_email: str | None = None


class FamilyAcceptRequest(BaseModel):
    invite_id: str
