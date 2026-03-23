import os

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.debug.logging_config import setup_logging
from app.routers.auth import router as auth_router
from app.routers.calendar import router as calendar_router
from app.routers.chat import router as chat_router
from app.routers.chat_history import router as chat_history_router
from app.routers.devices import router as devices_router
from app.routers.pets import router as pets_router
from app.routers.reminders import router as reminders_router
from app.middleware.rate_limit import ChatRateLimitMiddleware
from app.debug.middleware import (
    CorrelationMiddleware,
    RequestLoggingMiddleware,
    ErrorCaptureMiddleware,
)
from app.debug.error_types import PetPalError
from app.debug.exception_handlers import register_exception_handlers

# Set up JSON logging first
setup_logging()

app = FastAPI(title="PetPal API", version="0.1.0")

# Register exception handlers (logs 4xx/5xx with module context)
register_exception_handlers(app)

# CORS — allow all origins during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(pets_router)
app.include_router(calendar_router)
app.include_router(reminders_router)
app.include_router(chat_router)
app.include_router(chat_history_router)
app.include_router(devices_router)

# Register middleware (outermost runs first — last add = outermost)
app.add_middleware(ChatRateLimitMiddleware)
app.add_middleware(ErrorCaptureMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationMiddleware)


# Serve temp images for LLM vision (proxy doesn't support base64)
_temp_img_dir = Path(__file__).resolve().parent / "uploads" / "temp_images"
_temp_img_dir.mkdir(parents=True, exist_ok=True)
app.mount("/temp-images", StaticFiles(directory=str(_temp_img_dir)), name="temp-images")


@app.get("/health")
async def health():
    return {"status": "ok"}


# Only register dev-only routes outside production
if os.getenv("APP_ENV") != "production":

    @app.get("/debug/test-error")
    async def test_error():
        """Dev-only endpoint to test error capture pipeline."""
        raise PetPalError(
            "Test error for debug pipeline verification",
            context={"triggered_by": "test-error endpoint"},
        )
