import os

from fastapi import FastAPI
from app.debug.logging_config import setup_logging
from app.debug.middleware import (
    CorrelationMiddleware,
    RequestLoggingMiddleware,
    ErrorCaptureMiddleware,
)
from app.debug.error_types import PetPalError

# Set up JSON logging first
setup_logging()

app = FastAPI(title="PetPal API", version="0.1.0")

# Register middleware (outermost runs first — last add = outermost)
app.add_middleware(ErrorCaptureMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationMiddleware)


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
