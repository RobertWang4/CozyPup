import json

from pydantic import BaseModel


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    cards: list[dict] | None = None
    created_at: str


class ChatSessionResponse(BaseModel):
    id: str
    session_date: str
    created_at: str
    message_count: int
    is_saved: bool = False
    title: str | None = None
    expires_at: str | None = None


class SaveSessionResponse(BaseModel):
    title: str
    is_saved: bool


class SessionItem(BaseModel):
    id: str
    title: str | None = None
    session_date: str
    expires_at: str | None = None
    is_saved: bool
    message_count: int


class SavedSessionsResponse(BaseModel):
    saved: list[SessionItem]
    recent: list[SessionItem]


class TempSaveResponse(BaseModel):
    expires_at: str
    is_saved: bool


class ResumeResponse(BaseModel):
    session_id: str
    messages: list[ChatMessageResponse]
