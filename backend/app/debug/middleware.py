"""FastAPI middleware for correlation, request logging, and error capture."""

import json
import logging
import time
import traceback as tb

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

# ---------- Route → module mapping ----------
# Maps URL prefixes to the source module that handles them.
# Used by error capture to tag snapshots with the correct module.

ROUTE_MODULE_MAP = {
    "/api/v1/auth": "app.routers.auth",
    "/api/v1/pets": "app.routers.pets",
    "/api/v1/calendar": "app.routers.calendar",
    "/api/v1/reminders": "app.routers.reminders",
    "/api/v1/chat/history": "app.routers.chat_history",
    "/api/v1/chat/sessions": "app.routers.chat_history",
    "/api/v1/chat": "app.routers.chat",
    "/api/v1/devices": "app.routers.devices",
    "/api/v1/speech": "app.routers.speech_ws",
}


def _resolve_module(path: str) -> str:
    """Resolve a request path to the handling module name."""
    for prefix, module in ROUTE_MODULE_MAP.items():
        if path.startswith(prefix):
            return module
    return "app.unknown"


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Generates a correlation ID and extracts user context from JWT."""

    async def dispatch(self, request: Request, call_next) -> Response:
        cid = request.headers.get("X-Correlation-ID") or generate_correlation_id()
        set_correlation_id(cid)

        # Extract user_id from JWT Bearer token (without full verification — just for logging)
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                import jwt as pyjwt

                payload = pyjwt.decode(
                    auth_header[7:],
                    options={"verify_signature": False},  # just extract, don't verify
                )
                uid = payload.get("sub", "")
                if uid:
                    set_user_id(uid)
            except Exception:
                pass

        # Fallback to explicit header
        if not auth_header:
            user_id = request.headers.get("X-User-ID", "")
            if user_id:
                set_user_id(user_id)

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs request start/end with module context and captures 4xx/5xx details."""

    async def dispatch(self, request: Request, call_next) -> Response:
        method = request.method
        path = request.url.path
        module = _resolve_module(path)
        module_logger = logging.getLogger(module)

        module_logger.info(
            "request_start",
            extra={"method": method, "path": path, "src_module": module},
        )
        start = time.monotonic()

        response = await call_next(request)

        duration_ms = (time.monotonic() - start) * 1000
        status = response.status_code
        log_extra = {
            "method": method,
            "path": path,
            "src_module": module,
            "status": status,
            "duration_ms": round(duration_ms, 1),
        }

        if status >= 500:
            module_logger.error("request_error", extra=log_extra)
        elif status >= 400:
            module_logger.warning("request_client_error", extra=log_extra)
        else:
            module_logger.info("request_complete", extra=log_extra)

        return response


class ErrorCaptureMiddleware(BaseHTTPMiddleware):
    """Catches unhandled exceptions, captures snapshots with full request context."""

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            cid = get_correlation_id()
            path = request.url.path
            module = _resolve_module(path)
            module_logger = logging.getLogger(module)

            module_logger.exception(
                "unhandled_exception",
                extra={"src_module": module, "path": path},
            )

            # Build request_data for snapshot
            request_data = {
                "method": request.method,
                "path": path,
                "query": str(request.query_params),
            }

            try:
                from .error_capture import capture_error, save_snapshot

                snapshot = capture_error(exc, request_data=request_data)
                snapshot.module = module
                save_snapshot(snapshot)
                module_logger.error(
                    "error_snapshot_saved",
                    extra={
                        "correlation_id": cid,
                        "fingerprint": snapshot.fingerprint,
                        "src_module": module,
                        "error_type": snapshot.error_type,
                    },
                )
            except Exception:
                module_logger.warning("error_capture failed, skipping snapshot")

            return JSONResponse(
                status_code=500,
                content={
                    "error": str(exc),
                    "correlation_id": cid,
                    "src_module": module,
                },
            )
