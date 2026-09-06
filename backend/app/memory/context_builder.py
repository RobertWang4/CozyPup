from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.retrieval import retrieve_memweaver_context
from app.memory.types import RetrievedContext

logger = logging.getLogger(__name__)

RetrieveFn = Callable[..., Awaitable[RetrievedContext]]


def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def _single_pet_hint(pets: list | None) -> tuple[uuid.UUID | None, str | None]:
    if not pets or len(pets) != 1:
        return None, None
    pet = pets[0]
    pet_id = _get_attr(pet, "id")
    species = _get_attr(pet, "species")
    species_val = species.value if hasattr(species, "value") else species
    return pet_id, str(species_val) if species_val else None


async def build_memory_context(
    *,
    message: str,
    db: AsyncSession | None,
    user_id: uuid.UUID | None,
    pets: list | None = None,
    include_knowledge: bool = True,
    retrieve: RetrieveFn = retrieve_memweaver_context,
    timeout_ms: int | None = 250,
    session_factory: Callable[[], Any] | None = None,
) -> RetrievedContext:
    if not message.strip() or db is None or user_id is None:
        return RetrievedContext()

    pet_id, species = _single_pet_hint(pets)

    # Retrieval runs on its OWN session, never the request's. A timeout cancels
    # the query mid-flight; rolling back the shared session to recover would
    # expire every ORM object already loaded for the turn (pets, chat session),
    # and the next attribute access outside greenlet context raised
    # MissingGreenlet — every new user's first message failed this way.
    if session_factory is None:
        from app.database import async_session as session_factory

    async def _retrieve() -> RetrievedContext:
        async with session_factory() as own_db:
            return await retrieve(
                query=message,
                db=own_db,
                user_id=user_id,
                pet_id=pet_id,
                species=species,
                include_knowledge=include_knowledge,
            )

    try:
        if timeout_ms is None:
            return await _retrieve()
        async with asyncio.timeout(timeout_ms / 1000):
            return await _retrieve()
    except TimeoutError:
        logger.info("memory_context_build_timeout", extra={"timeout_ms": timeout_ms})
    except Exception as exc:
        logger.warning("memory_context_build_error", extra={"error": str(exc)[:200]})
    return RetrievedContext()
