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
    transaction_id: str
    product_id: str


class VerifyResponse(BaseModel):
    status: str
    expires_at: datetime | None = None
