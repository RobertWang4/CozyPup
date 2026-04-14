"""Process-local feature flag cache.

The backend periodically refreshes flags from the `feature_flags` DB table and
holds them in a local dict. Callers use `get_flag(key, default)` to read the
current value. Writes go through the admin ops routes, which also update the
local cache directly for sub-second visibility on the writing instance.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlalchemy import select

logger = logging.getLogger("cozypup.flags")

REFRESH_INTERVAL_SECONDS = 30.0

_cache: dict[str, Any] = {}
_cache_loaded_at: float = 0.0
_lock = asyncio.Lock()


def get_flag(key: str, default: Any = None) -> Any:
    """Return the flag value, or `default` if missing."""
    return _cache.get(key, default)


def get_bool_flag(key: str, *, default: bool) -> bool:
    v = _cache.get(key, default)
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.lower() in ("1", "true", "yes", "on")
    return default


def get_int_flag(key: str, *, default: int) -> int:
    v = _cache.get(key, default)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _set_in_cache(key: str, value: Any) -> None:
    """Direct cache write. Used by the refresher and by admin ops routes to
    make a just-written flag visible without waiting for the next refresh."""
    _cache[key] = value


async def refresh_now() -> int:
    """Reload the cache from the DB. Returns the number of flags loaded."""
    from app.database import async_session
    from app.models import FeatureFlag

    global _cache_loaded_at
    async with _lock:
        try:
            async with async_session() as db:
                rows = (await db.execute(select(FeatureFlag))).scalars().all()
                new_cache = {row.key: row.value for row in rows}
        except Exception as e:
            logger.warning("flag refresh failed: %s", e)
            return len(_cache)
        _cache.clear()
        _cache.update(new_cache)
        _cache_loaded_at = time.monotonic()
        logger.info("flag cache refreshed: %d keys", len(_cache))
        return len(_cache)


async def run_refresher() -> None:
    """Background task: refresh every REFRESH_INTERVAL_SECONDS."""
    while True:
        await refresh_now()
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
