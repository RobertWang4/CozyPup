"""Public feature flag endpoint consumed by the iOS app (read-only subset)."""
from fastapi import APIRouter

from app import flags as flag_module

flags_router = APIRouter(prefix="/api/v1/flags", tags=["flags"])

# Only these keys are exposed publicly. Never add secrets here.
_PUBLIC_KEYS = {
    "broadcast_banner",
    "chat_rate_limit_per_hour",
}


@flags_router.get("/public")
async def public_flags() -> dict:
    return {k: flag_module.get_flag(k, default=None) for k in _PUBLIC_KEYS}
