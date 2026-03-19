from pydantic import BaseModel

from app.models import EventCategory, EventSource, EventType


class CalendarEventCreate(BaseModel):
    pet_id: str
    event_date: str  # YYYY-MM-DD
    event_time: str | None = None  # HH:MM
    title: str
    type: EventType = EventType.log
    category: EventCategory = EventCategory.daily
    raw_text: str = ""
    source: EventSource = EventSource.manual


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    category: EventCategory | None = None
    event_date: str | None = None
    event_time: str | None = None


class CalendarEventResponse(BaseModel):
    id: str
    pet_id: str
    pet_name: str
    pet_color_hex: str
    event_date: str
    event_time: str | None
    title: str
    type: EventType
    category: EventCategory
    raw_text: str
    source: EventSource
    edited: bool
    created_at: str
