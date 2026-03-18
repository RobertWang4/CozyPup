"""FastAPI middleware for correlation, request logging, and error capture."""

import json
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .correlation import (
    generate_correlation_id,
    get_correlation_id,
    set_correlation_id,
    set_user_id,
)

logger = logging.getLogger(__name__)


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Generates a correlation ID for each request and sets context vars."""

    async def dispatch(self, request: Request, call_next) -> Response:
        cid = request.headers.get("X-Correlation-ID") or generate_correlation_id()
        set_correlation_id(cid)

        # Read user ID from request header if present
        user_id = request.headers.get("X-User-ID", "")
        if user_id:
            set_user_id(user_id)

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs request start (method, path) and end (status, duration_ms)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        method = request.method
        path = request.url.path

        logger.info("Request started: %s %s", method, path)
        start = time.monotonic()

        response = await call_next(request)

        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "Request finished: %s %s status=%d duration_ms=%.1f",
            method,
            path,
            response.status_code,
            duration_ms,
        )
        return response


class ErrorCaptureMiddleware(BaseHTTPMiddleware):
    """Catches unhandled exceptions and returns a structured 500 response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            cid = get_correlation_id()
            logger.exception("Unhandled exception during request")

            # Lazy import to avoid circular dependency — error_capture may not exist yet
            try:
                from .error_capture import capture_error, save_snapshot

                snapshot = capture_error(exc)
                save_snapshot(snapshot)
            except Exception:
                logger.warning("error_capture module not available or failed, skipping snapshot")

            return JSONResponse(
                status_code=500,
                content={
                    # TODO: In production, replace str(exc) with "Internal server error" to avoid leaking internals
                    "error": str(exc),
                    "correlation_id": cid,
                },
            )
