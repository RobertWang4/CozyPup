"""get_vaccine_schedule / get_deworming_schedule tools.

Structured, deterministic lookups for vaccination and deworming SCHEDULES
(timing + vaccine/parasite name + authoritative citation). Used in place
of RAG for scheduling questions so answers are 100% traceable to
AAHA / AAFP / CAPC guidelines.

These tools intentionally do NOT return dosage. Dosage is a vet-only
decision; CozyPup refuses dosage questions at the prompt layer.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.registry import register_tool

logger = logging.getLogger(__name__)

_ALLOWED_SPECIES = {"dog", "cat"}
_ALLOWED_LIFE_STAGES = {"puppy_kitten", "adult", "pregnant", "senior"}


def _row_to_vaccine_dict(row) -> dict:
    return {
        "species": row.species,
        "vaccine_name": row.vaccine_name,
        "core": bool(row.core),
        "age_weeks_start": row.age_weeks_start,
        "age_weeks_end": row.age_weeks_end,
        "interval_description": row.interval_description,
        "notes": row.notes,
        "source_url": row.source_url,
        "source_name": row.source_name,
    }


def _row_to_deworming_dict(row) -> dict:
    return {
        "species": row.species,
        "parasite_category": row.parasite_category,
        "life_stage": row.life_stage,
        "interval_description": row.interval_description,
        "notes": row.notes,
        "source_url": row.source_url,
        "source_name": row.source_name,
    }


async def get_vaccine_schedule(
    species: str,
    age_weeks: int | None = None,
    *,
    db: AsyncSession,
) -> list[dict]:
    """Return vaccine schedule rows for a species.

    If `age_weeks` is provided, filters to entries whose age window
    overlaps the supplied age (i.e. entries still relevant for a pet of
    that age — open-ended boosters always included).

    Each dict carries `source_url` and `source_name` so the LLM can cite.
    """
    species = (species or "").lower().strip()
    if species not in _ALLOWED_SPECIES:
        return []

    result = await db.execute(
        text(
            "SELECT species, vaccine_name, core, age_weeks_start, age_weeks_end, "
            "interval_description, notes, source_url, source_name "
            "FROM vaccine_schedule WHERE species = :species "
            "ORDER BY core DESC, vaccine_name"
        ),
        {"species": species},
    )
    rows = [_row_to_vaccine_dict(r) for r in result.fetchall()]

    if age_weeks is not None:
        filtered = []
        for r in rows:
            start = r["age_weeks_start"]
            end = r["age_weeks_end"]
            # Open-ended (adult booster) rows always included
            if end is None:
                filtered.append(r)
                continue
            if start is None:
                start = 0
            if start <= age_weeks <= end or age_weeks <= end:
                filtered.append(r)
        rows = filtered

    return rows


async def get_deworming_schedule(
    species: str,
    life_stage: str | None = None,
    *,
    db: AsyncSession,
) -> list[dict]:
    """Return deworming schedule rows for a species, optionally filtered by life_stage.

    Each dict carries `source_url` and `source_name` for citation.
    """
    species = (species or "").lower().strip()
    if species not in _ALLOWED_SPECIES:
        return []

    params: dict = {"species": species}
    q = (
        "SELECT species, parasite_category, life_stage, interval_description, "
        "notes, source_url, source_name FROM deworming_schedule "
        "WHERE species = :species"
    )
    if life_stage:
        if life_stage not in _ALLOWED_LIFE_STAGES:
            return []
        q += " AND life_stage = :life_stage"
        params["life_stage"] = life_stage
    q += " ORDER BY parasite_category, life_stage"

    result = await db.execute(text(q), params)
    return [_row_to_deworming_dict(r) for r in result.fetchall()]


# ---- Tool registry wrappers -------------------------------------------------


@register_tool("get_vaccine_schedule")
async def _tool_get_vaccine_schedule(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    species = arguments.get("species", "")
    age_weeks = arguments.get("age_weeks")
    if age_weeks is not None:
        try:
            age_weeks = int(age_weeks)
        except (TypeError, ValueError):
            age_weeks = None
    try:
        rows = await get_vaccine_schedule(species, age_weeks, db=db)
    except Exception as exc:
        logger.error("get_vaccine_schedule_error", extra={"error": str(exc)[:200]})
        return {"success": False, "error": "Schedule lookup failed.", "results": []}

    return {
        "success": True,
        "results": rows,
        "disclaimer": (
            "Timing guidance only; dosage and medical decisions require a "
            "licensed veterinarian."
        ),
    }


@register_tool("get_deworming_schedule")
async def _tool_get_deworming_schedule(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    species = arguments.get("species", "")
    life_stage = arguments.get("life_stage")
    try:
        rows = await get_deworming_schedule(species, life_stage, db=db)
    except Exception as exc:
        logger.error("get_deworming_schedule_error", extra={"error": str(exc)[:200]})
        return {"success": False, "error": "Schedule lookup failed.", "results": []}

    return {
        "success": True,
        "results": rows,
        "disclaimer": (
            "Timing guidance only; dosage and medical decisions require a "
            "licensed veterinarian."
        ),
    }
