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


class LocationUpdate(BaseModel):
    location_name: str
    location_address: str = ""
    location_lat: float
    location_lng: float
    place_id: str = ""


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    category: EventCategory | None = None
    event_date: str | None = None
    event_time: str | None = None
    cost: float | None = None


class PetTag(BaseModel):
    id: str
    name: str
    color_hex: str


class CalendarEventResponse(BaseModel):
    id: str
    pet_id: str | None = None
    pet_name: str = ""
    pet_color_hex: str = ""
    pet_tags: list[PetTag] = []  # multi-pet support
    event_date: str
    event_time: str | None
    title: str
    type: EventType
    category: EventCategory
    raw_text: str
    source: EventSource
    edited: bool
    photos: list[str] = []
    location_name: str | None = None
    location_address: str | None = None
    location_lat: float | None = None
    location_lng: float | None = None
    place_id: str | None = None
    cost: float | None = None
    reminder_at: str | None = None
    created_at: str
