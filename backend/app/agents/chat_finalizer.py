"""Small finalization helpers for one chat turn.

The router still owns DB persistence and SSE emission. These helpers keep
Phase 4 policy and serialization decisions in one tested place.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.agents.constants import NUDGE_TOOLS
from app.agents.pre_processing.types import SuggestedAction

logger = logging.getLogger(__name__)

SaveMessageFn = Callable[..., Awaitable[Any]]
TrackTaskFn = Callable[[Awaitable[None]], Any]
AsyncSessionFactory = Callable[[], Any]
UpsertMemoryFn = Callable[..., Awaitable[Any]]
TriggerSummaryFn = Callable[..., Awaitable[Any]]
MergeProfileFn = Callable[..., Awaitable[str | None]]
LogChatTurnFn = Callable[..., None]
ExtractRetrievedChunksFn = Callable[[list[dict]], list[dict]]
GetCorrelationIdFn = Callable[[], str | None]


@dataclass(frozen=True)
class ChatTurnFinalization:
    all_cards: list[dict]
    cards_json: str | None
    assistant_message: Any


def chat_turn_memory_source_id(assistant_message: Any) -> uuid.UUID:
    return assistant_message.id


def should_run_final_fallback(
    result: Any,
    suggested_actions: list[SuggestedAction],
    *,
    nudge_tools: set[str] = NUDGE_TOOLS,
) -> bool:
    no_tools_called = (
        not getattr(result, "cards", [])
        and not getattr(result, "confirm_cards", [])
        and not getattr(result, "tools_called", set())
    )
    if not no_tools_called:
        return False

    return any(
        action.confidence >= 0.8 and action.tool_name in nudge_tools
        for action in suggested_actions
    )


def assistant_cards_json(result: Any) -> tuple[list[dict], str | None]:
    all_cards = [
        *getattr(result, "cards", []),
        *getattr(result, "confirm_cards", []),
    ]
    return all_cards, json.dumps(all_cards) if all_cards else None


def chat_turn_memory_content(user_message: str, assistant_text: str) -> str:
    return f"用户: {user_message}\n助手: {assistant_text[:500]}"


async def apply_profile_extraction(
    *,
    extractor_task: Awaitable[dict | None],
    pets: list[Any],
    db: Any,
    lang: str,
    merge_profile: MergeProfileFn | None = None,
) -> bool:
    """Merge profile extraction output into the matching pet profile."""
    try:
        extracted = await extractor_task
        if not extracted:
            return False

        pet_id = str(extracted.get("pet_id") or "")
        info = extracted.get("info") or {}
        if not pet_id or not info:
            return False

        target_pet = next((p for p in pets if str(p.id) == pet_id), None)
        if target_pet is None:
            return False

        if merge_profile is None:
            from app.agents.profile_extractor import merge_into_profile_md as merge_profile

        new_md = await merge_profile(target_pet, info, lang=lang)
        if not new_md:
            return False

        target_pet.profile_md = new_md
        await db.commit()
        logger.info("profile_extractor_saved", extra={
            "keys": list(info.keys()),
            "md_length": len(new_md),
        })
        return True
    except Exception as exc:
        logger.warning("profile_extractor_save_error", extra={"error": str(exc)[:200]})
        return False


def record_chat_audit(
    *,
    user_id: uuid.UUID,
    pets: list[Any],
    raw_query: str,
    is_emergency_route: bool,
    all_cards: list[dict],
    llm_output: str | None,
    response_time_ms: int,
    model_used: str | None,
    session_id: str,
    lang: str,
    tools_called: set[str] | list[str] | tuple[str, ...] | None,
    keyword_emergency: bool,
    client_version: str | None,
    metadata_extra: dict | None = None,
    log_chat_turn: LogChatTurnFn | None = None,
    extract_retrieved_chunks: ExtractRetrievedChunksFn | None = None,
    get_correlation_id: GetCorrelationIdFn | None = None,
) -> bool:
    """Write the chat legal audit hook without letting failures affect chat."""
    try:
        if log_chat_turn is None:
            from app.services.chat_audit import log_chat_turn as log_chat_turn
        if extract_retrieved_chunks is None:
            from app.services.chat_audit import extract_retrieved_chunks as extract_retrieved_chunks
        if get_correlation_id is None:
            from app.debug.correlation import get_correlation_id as get_correlation_id

        audit_pet_id = pets[0].id if pets else None
        audit_species = (
            getattr(pets[0].species, "value", str(pets[0].species)) if pets else None
        )
        metadata_json = {
            "session_id": session_id,
            "lang": lang,
            "tools_called": sorted(tools_called) if tools_called else [],
            "keyword_emergency": bool(keyword_emergency),
            "correlation_id": get_correlation_id(),
            "client_version": client_version,
        }
        if metadata_extra:
            metadata_json.update(metadata_extra)

        log_chat_turn(
            user_id=user_id,
            pet_id=audit_pet_id,
            species=audit_species,
            raw_query=raw_query or "",
            is_emergency_route=is_emergency_route,
            retrieved_chunks=extract_retrieved_chunks(all_cards),
            llm_output=llm_output,
            response_time_ms=response_time_ms,
            model_used=model_used,
            metadata_json=metadata_json,
        )
        return True
    except Exception as exc:  # noqa: BLE001 — audit must never break the stream
        logger.warning("chat_audit_hook_error", extra={"error": str(exc)[:300]})
        return False


async def finalize_assistant_turn(
    *,
    db: Any,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    assistant_role: Any,
    result: Any,
    user_message: str,
    lang: str,
    save_message: SaveMessageFn,
    track_task: TrackTaskFn,
    async_session_factory: AsyncSessionFactory | None = None,
    upsert_memory: UpsertMemoryFn | None = None,
    trigger_summary: TriggerSummaryFn | None = None,
) -> ChatTurnFinalization:
    if async_session_factory is None:
        from app.database import async_session as async_session_factory
    if upsert_memory is None:
        from app.memory.store import upsert_behavioral_memory as upsert_memory
    if trigger_summary is None:
        from app.agents.context_agent import trigger_summary_if_needed as trigger_summary

    all_cards, cards_json = assistant_cards_json(result)
    assistant_message = await save_message(
        db,
        session_id,
        user_id,
        assistant_role,
        result.response_text,
        cards_json,
    )
    source_id = chat_turn_memory_source_id(assistant_message)

    async def _write_memory_bg() -> None:
        try:
            memory_content = chat_turn_memory_content(user_message, result.response_text)
            async with async_session_factory() as bg_db:
                await upsert_memory(
                    db=bg_db,
                    user_id=user_id,
                    source_kind="chat_turn",
                    source_id=source_id,
                    content=memory_content,
                )
        except Exception as exc:
            logger.warning("memory_bg_error", extra={"error": str(exc)[:200]})

    async def _summarize_bg() -> None:
        try:
            async with async_session_factory() as bg_db:
                await trigger_summary(session_id, bg_db, lang=lang)
        except Exception as exc:
            logger.warning("summary_bg_error", extra={"error": str(exc)[:200]})

    track_task(_write_memory_bg())
    track_task(_summarize_bg())

    return ChatTurnFinalization(
        all_cards=all_cards,
        cards_json=cards_json,
        assistant_message=assistant_message,
    )
