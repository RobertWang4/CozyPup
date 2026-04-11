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
from app.routers.places import router as places_router
from app.routers.tasks import router as tasks_router
from app.routers.subscription import router as subscription_router
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
app.include_router(tasks_router)
app.include_router(places_router)
app.include_router(subscription_router)

# Register middleware (outermost runs first — last add = outermost)
app.add_middleware(ChatRateLimitMiddleware)
app.add_middleware(ErrorCaptureMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationMiddleware)



@app.on_event("startup")
async def _fix_avatar_urls():
    """One-time fix: convert GCS absolute URLs to relative paths."""
    import asyncio
    import logging
    from app.database import async_session
    from sqlalchemy import text
    logger = logging.getLogger(__name__)
    try:
        async with asyncio.timeout(10):
            async with async_session() as s:
                r = await s.execute(text(
                    "UPDATE pets SET avatar_url = '/api/v1/pets/' || id::text || '/avatar' "
                    "WHERE avatar_url LIKE 'https://storage%'"
                ))
                if r.rowcount:
                    await s.commit()
                    logger.info(f"Fixed {r.rowcount} avatar URLs from GCS absolute to relative")
    except (Exception, asyncio.TimeoutError) as e:
        logger.warning(f"avatar URL fix skipped: {e}")


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
