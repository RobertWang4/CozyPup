"""In-memory rate limiter for chat endpoint."""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

MAX_MESSAGES_PER_HOUR = 30
MAX_MESSAGE_LENGTH = 2000
WINDOW_SECONDS = 3600


class _UserBucket:
    __slots__ = ("timestamps",)

    def __init__(self):
        self.timestamps: list[float] = []

    def is_allowed(self) -> bool:
        now = time.monotonic()
        # Prune expired entries
        self.timestamps = [t for t in self.timestamps if now - t < WINDOW_SECONDS]
        if len(self.timestamps) >= MAX_MESSAGES_PER_HOUR:
            return False
        self.timestamps.append(now)
        return True

    def retry_after(self) -> int:
        if not self.timestamps:
            return 0
        oldest = self.timestamps[0]
        return max(1, int(WINDOW_SECONDS - (time.monotonic() - oldest)))


_buckets: dict[str, _UserBucket] = defaultdict(_UserBucket)


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

        return await call_next(request)
