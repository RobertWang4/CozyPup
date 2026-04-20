"""Idempotent loader for vaccine_schedule and deworming_schedule tables.

Run AFTER `alembic upgrade head` has created the tables. Safe to re-run;
each row is replaced by its natural key:
  vaccine_schedule   (species, vaccine_name)
  deworming_schedule (species, parasite_category, life_stage)

Usage:
    python -m knowledge.seed.load_schedules
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import text

from app.database import async_session

SEED_DIR = Path(__file__).parent
VACCINES_FILE = SEED_DIR / "vaccines_us.json"
DEWORMING_FILE = SEED_DIR / "deworming_us.json"


async def load_vaccines() -> int:
    rows = json.loads(VACCINES_FILE.read_text())
    async with async_session() as db:
        for r in rows:
            if "TODO_VERIFY_URL" in (r.get("source_url") or ""):
                continue
            await db.execute(
                text(
                    "DELETE FROM vaccine_schedule "
                    "WHERE species = :species AND vaccine_name = :vaccine_name"
                ),
                {"species": r["species"], "vaccine_name": r["vaccine_name"]},
            )
            await db.execute(
                text(
                    "INSERT INTO vaccine_schedule "
                    "(species, vaccine_name, core, age_weeks_start, age_weeks_end, "
                    "interval_description, notes, source_url, source_name) "
                    "VALUES (:species, :vaccine_name, :core, :age_weeks_start, "
                    ":age_weeks_end, :interval_description, :notes, :source_url, "
                    ":source_name)"
                ),
                r,
            )
        await db.commit()
    return len([r for r in rows if "TODO_VERIFY_URL" not in (r.get("source_url") or "")])


async def load_deworming() -> int:
    rows = json.loads(DEWORMING_FILE.read_text())
    async with async_session() as db:
        for r in rows:
            if "TODO_VERIFY_URL" in (r.get("source_url") or ""):
                continue
            await db.execute(
                text(
                    "DELETE FROM deworming_schedule "
                    "WHERE species = :species "
                    "AND parasite_category = :parasite_category "
                    "AND life_stage = :life_stage"
                ),
                {
                    "species": r["species"],
                    "parasite_category": r["parasite_category"],
                    "life_stage": r["life_stage"],
                },
            )
            await db.execute(
                text(
                    "INSERT INTO deworming_schedule "
                    "(species, parasite_category, life_stage, "
                    "interval_description, notes, source_url, source_name) "
                    "VALUES (:species, :parasite_category, :life_stage, "
                    ":interval_description, :notes, :source_url, :source_name)"
                ),
                r,
            )
        await db.commit()
    return len([r for r in rows if "TODO_VERIFY_URL" not in (r.get("source_url") or "")])


async def main() -> None:
    v = await load_vaccines()
    d = await load_deworming()
    print(f"Seeded vaccine_schedule: {v} rows")
    print(f"Seeded deworming_schedule: {d} rows")


if __name__ == "__main__":
    asyncio.run(main())
