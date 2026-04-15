from pydantic import BaseModel
from datetime import datetime


class SubscriptionStatusResponse(BaseModel):
    status: str  # "trial" | "active" | "expired"
    trial_days_left: int | None = None
    expires_at: datetime | None = None
    product_id: str | None = None
    is_duo: bool = False


class TrialStatsResponse(BaseModel):
    chat_count: int
    reminder_count: int
    event_count: int


class VerifyRequest(BaseModel):
    # Raw JWS string from StoreKit 2 VerificationResult.jwsRepresentation.
    # Backend verifies the signature chain against Apple's root CAs; we do NOT
    # trust any transaction fields outside of this verified payload.
    signed_transaction: str
    # Optional hint: client tells us whether it's a sandbox or production build.
    # True = sandbox (DEBUG/TestFlight), False = production. Missing = use settings default.
    sandbox: bool | None = None


class VerifyResponse(BaseModel):
    status: str
    expires_at: datetime | None = None
