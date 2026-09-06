"""Small context object passed through tool dispatch helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolDispatchContext:
    db: Any = None
    user_id: Any = None
    session_id: Any = None
    result: Any = None
    on_card: Callable | None = None
    lang: str = "zh"
    pets: list[Any] | None = None
    images: list[str] | None = None
    image_urls: list[str] | None = None
    recent_image_urls: list[str] | None = None
    location: dict[str, Any] | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    confirm_action_id: str = ""   # graph thread id, stamped onto confirm cards
