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
