"""Fire-and-forget audit logging for every chat turn.

Writes one row per turn to `chat_audit_log` (Postgres). Used as legal
evidence for the pet-health product (US/Canada, 2+ year retention).

Contract: `log_chat_turn(...)` MUST NOT raise and MUST NOT block the
user-facing response. All failures are swallowed and logged.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Iterable

from app.database import async_session
from app.models import ChatAuditLog

logger = logging.getLogger(__name__)


def extract_retrieved_chunks(cards: Iterable[dict] | None) -> list[dict]:
    """Pull knowledge-source items out of a `references` card.

    The RAG tool emits {"type": "references", "items": [...]}. Each
    knowledge item has title/url; distance is not surfaced to the card,
    so we store None when unavailable.
    """
    if not cards:
        return []
    out: list[dict] = []
    for card in cards:
        if not isinstance(card, dict) or card.get("type") != "references":
            continue
        for item in card.get("items") or []:
            if item.get("source") != "knowledge":
                continue
            out.append({
                "title": item.get("title"),
                "url": item.get("url"),
                "distance": item.get("distance"),
            })
    return out


async def _write_audit_row(**fields: Any) -> None:
    try:
        async with async_session() as db:
            db.add(ChatAuditLog(**fields))
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — audit must never raise
        logger.warning(
            "chat_audit_write_failed",
            extra={"error_type": type(exc).__name__, "error": str(exc)[:300]},
        )


def log_chat_turn(
    *,
    user_id: uuid.UUID,
    raw_query: str,
    pet_id: uuid.UUID | None = None,
    species: str | None = None,
    is_emergency_route: bool = False,
    retrieved_chunks: list[dict] | None = None,
    llm_output: str | None = None,
    response_time_ms: int | None = None,
    model_used: str | None = None,
    metadata_json: dict | None = None,
) -> None:
    """Schedule an audit row write. Returns immediately.

    Safe to call from inside a request handler — the DB write runs on
    its own session in a background task and never raises.
    """
    coro = _write_audit_row(
        user_id=user_id,
        pet_id=pet_id,
        species=species,
        raw_query=raw_query or "",
        is_emergency_route=bool(is_emergency_route),
        retrieved_chunks=retrieved_chunks or [],
        llm_output=llm_output,
        response_time_ms=response_time_ms,
        model_used=model_used,
        metadata_json=metadata_json,
    )
    try:
        task = asyncio.create_task(coro)
        # Prevent "Task was destroyed but it is pending!" warnings.
        _pending.add(task)
        task.add_done_callback(_pending.discard)
    except RuntimeError:
        logger.warning("chat_audit_no_running_loop")


_pending: set[asyncio.Task] = set()
