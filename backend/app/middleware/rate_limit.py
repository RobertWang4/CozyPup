"""In-memory rate limiter for chat endpoint."""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

MAX_MESSAGES_PER_HOUR = 30
MAX_MESSAGE_LENGTH = 2000
WINDOW_SECONDS = 3600
# Global cap on LLM chats per UTC day across all users — a cost guard while the
# app is free. Override with the `daily_chat_cap` flag; 0 disables the cap.
DAILY_CHAT_CAP = 2000


class _UserBucket:
    __slots__ = ("timestamps",)

    def __init__(self):
        self.timestamps: list[float] = []

    def is_allowed(self) -> bool:
        now = time.monotonic()
        # Prune expired entries
        self.timestamps = [t for t in self.timestamps if now - t < WINDOW_SECONDS]
        if len(self.timestamps) >= current_limit_per_hour():
            return False
        self.timestamps.append(now)
        return True

    def retry_after(self) -> int:
        if not self.timestamps:
            return 0
        oldest = self.timestamps[0]
        return max(1, int(WINDOW_SECONDS - (time.monotonic() - oldest)))


_buckets: dict[str, _UserBucket] = defaultdict(_UserBucket)


def clear(user_key: str | None) -> int:
    """Admin helper: wipe rate-limit state. Returns number of buckets cleared."""
    if user_key is None:
        n = len(_buckets)
        _buckets.clear()
        return n
    if user_key in _buckets:
        del _buckets[user_key]
        return 1
    return 0


_daily: dict[str, int] = {"day": "", "count": 0}


def reset_daily_counter() -> None:
    _daily["day"] = ""
    _daily["count"] = 0


def _daily_cap_reached() -> bool:
    """Increment today's global counter; True if the cap is already hit."""
    try:
        from app.flags import get_int_flag
        cap = get_int_flag("daily_chat_cap", default=DAILY_CHAT_CAP)
    except Exception:
        cap = DAILY_CHAT_CAP
    if cap <= 0:
        return False
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if _daily["day"] != today:
        _daily["day"] = today
        _daily["count"] = 0
    if _daily["count"] >= cap:
        return True
    _daily["count"] += 1
    return False


def current_limit_per_hour() -> int:
    """Read the chat_rate_limit_per_hour flag, falling back to the constant."""
    try:
        from app.flags import get_int_flag
        return get_int_flag("chat_rate_limit_per_hour", default=MAX_MESSAGES_PER_HOUR)
    except Exception:
        return MAX_MESSAGES_PER_HOUR


class ChatRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only apply to POST /api/v1/chat
        if request.method == "POST" and request.url.path == "/api/v1/chat":
            # Check message length (not total body — images are large)
            body = await request.body()
            try:
                import json as _json
                msg_text = _json.loads(body).get("message", "")
                if len(msg_text) > MAX_MESSAGE_LENGTH:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Message too long (max {MAX_MESSAGE_LENGTH} characters)",
                    )
            except (ValueError, AttributeError):
                pass

            # Extract user from auth header for rate limiting
            auth = request.headers.get("authorization", "")
            # Use the token itself as key (unique per user)
            key = auth[-16:] if auth else request.client.host if request.client else "unknown"

            bucket = _buckets[key]
            if not bucket.is_allowed():
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(bucket.retry_after())},
                )

            if _daily_cap_reached():
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Daily chat capacity reached, please try again tomorrow",
                    headers={"Retry-After": "3600"},
                )

        return await call_next(request)
