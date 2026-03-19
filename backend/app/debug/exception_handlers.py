"""Global exception handlers that log all errors with module context."""

import json
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .correlation import get_correlation_id
from .middleware import _resolve_module


def register_exception_handlers(app: FastAPI):
    """Register exception handlers that log 4xx/5xx with module-level precision."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        cid = get_correlation_id()
        path = request.url.path
        module = _resolve_module(path)
        module_logger = logging.getLogger(module)

        log_data = {
            "src_module": module,
            "path": path,
            "method": request.method,
            "status": exc.status_code,
            "detail": exc.detail,
            "correlation_id": cid,
        }

        if exc.status_code >= 500:
            module_logger.error("http_error", extra=log_data)
        elif exc.status_code >= 400:
            module_logger.warning("http_client_error", extra=log_data)

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "correlation_id": cid,
                "src_module": module,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        cid = get_correlation_id()
        path = request.url.path
        module = _resolve_module(path)
        module_logger = logging.getLogger(module)

        errors = exc.errors()
        module_logger.warning(
            "validation_error",
            extra={
                "src_module": module,
                "path": path,
                "method": request.method,
                "errors": errors,
                "correlation_id": cid,
            },
        )

        return JSONResponse(
            status_code=422,
            content={
                "detail": errors,
                "correlation_id": cid,
                "src_module": module,
            },
        )
