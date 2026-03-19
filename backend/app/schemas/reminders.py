from pydantic import BaseModel


class ReminderCreate(BaseModel):
    pet_id: str
    type: str  # "medication", "vaccine", "checkup"
    title: str
    body: str = ""
    trigger_at: str  # ISO8601 datetime


class ReminderUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    trigger_at: str | None = None


class ReminderResponse(BaseModel):
    id: str
    pet_id: str
    pet_name: str
    type: str
    title: str
    body: str
    trigger_at: str
    sent: bool
    created_at: str
