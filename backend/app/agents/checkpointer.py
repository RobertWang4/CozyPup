"""Postgres checkpointer for the agent graph (LangGraph `interrupt` support).

One `AsyncPostgresSaver` per process, backed by a small `AsyncConnectionPool`
against the same database SQLAlchemy uses. The pool is opened in the app
startup hook and `setup()` creates the checkpoint tables once; a failure there
is logged and the app still boots — chat keeps working (the graph falls back to
an in-memory saver), only `POST /chat/confirm-action` starts answering 503.

Checkpoints only exist to resume a confirm interrupt, so they are small and
short-lived: `prune_checkpoints()` (wired to `admin ops checkpoints prune`)
drops every thread whose latest checkpoint is older than a cutoff.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.config import settings

logger = logging.getLogger(__name__)

_IMAGE_PLACEHOLDER = "data:image/redacted"

_saver = None
_pool = None


# ---------------------------------------------------------------------------
# Serializer — keep base64 images out of the checkpoint
# ---------------------------------------------------------------------------

def _redact_images(obj: Any) -> Any:
    """Replace `data:image/...` payloads with a short placeholder.

    `request_images` appends a multimodal user message whose `image_url` holds
    a full base64 data URI; a checkpoint carrying those would be megabytes.
    Resuming never calls the model again (the deferred tool is executed and the
    run goes straight to `finalize`), so the bytes are not needed after the
    interrupt.
    """
    if isinstance(obj, str):
        return _IMAGE_PLACEHOLDER if obj.startswith("data:image/") else obj
    if isinstance(obj, dict):
        return {k: _redact_images(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_images(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_redact_images(v) for v in obj)
    return obj


class RedactingSerializer(JsonPlusSerializer):
    """JsonPlusSerializer that strips base64 image data URIs on write."""

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        return super().dumps_typed(_redact_images(obj))


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def _psycopg_dsn() -> str:
    """`postgresql+asyncpg://…` → the plain DSN psycopg wants."""
    url = settings.database_url
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def make_pool():
    """Unopened `AsyncConnectionPool` for the checkpointer.

    Supabase session pooler on 5432: connections are scarce (hence a 1..3
    pool — psycopg's default min_size of 4 would exceed max_size) but
    prepared statements are fine.
    """
    from psycopg_pool import AsyncConnectionPool

    return AsyncConnectionPool(
        conninfo=_psycopg_dsn(),
        min_size=1,
        max_size=3,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )


async def setup_checkpointer() -> None:
    """Open the pool and create the checkpoint tables. Never raises."""
    global _saver, _pool
    if _saver is not None:
        return
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        pool = make_pool()
        await pool.open(wait=True, timeout=10)
        saver = AsyncPostgresSaver(pool, serde=RedactingSerializer())
        await saver.setup()
    except Exception as exc:
        logger.error("checkpointer_setup_failed", extra={"error": str(exc)[:300]})
        return
    _pool, _saver = pool, saver
    logger.info("checkpointer_ready")


async def close_checkpointer() -> None:
    global _saver, _pool
    _saver = None
    if _pool is not None:
        try:
            await _pool.close()
        except Exception as exc:
            logger.warning("checkpointer_close_error", extra={"error": str(exc)[:200]})
        _pool = None


def get_checkpointer():
    """The process-wide `AsyncPostgresSaver`, or None if setup failed."""
    return _saver


# ---------------------------------------------------------------------------
# Pruning — `admin ops checkpoints prune --before 7d`
# ---------------------------------------------------------------------------

_STALE_THREADS_SQL = (
    "SELECT thread_id FROM checkpoints GROUP BY thread_id "
    "HAVING max(checkpoint->>'ts') < %s"
)
_CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")


async def prune_checkpoints(older_than: timedelta, *, conn=None) -> int:
    """Delete every thread whose latest checkpoint predates the cutoff.

    Returns the number of threads deleted. Pass `conn` to use an existing
    psycopg connection (tests do); otherwise a pool connection is used.
    """
    cutoff = (datetime.now(timezone.utc) - older_than).isoformat()
    if conn is not None:
        return await _prune_with(conn, cutoff)
    if _pool is None:
        raise RuntimeError("checkpointer not configured")
    async with _pool.connection() as pooled:
        return await _prune_with(pooled, cutoff)


async def _prune_with(conn, cutoff: str) -> int:
    async with conn.cursor() as cur:
        await cur.execute(_STALE_THREADS_SQL, (cutoff,))
        thread_ids = [row[0] for row in await cur.fetchall()]
        if not thread_ids:
            return 0
        for table in _CHECKPOINT_TABLES:
            await cur.execute(
                f"DELETE FROM {table} WHERE thread_id = ANY(%s)", (thread_ids,)
            )
    return len(thread_ids)
