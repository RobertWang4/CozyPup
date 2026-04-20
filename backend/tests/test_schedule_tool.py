"""Unit tests for get_vaccine_schedule / get_deworming_schedule.

Uses an in-memory SQLite database with the two schedule tables created
manually (mirroring the Alembic migration). Seeds a few representative
rows and verifies the tool returns the right shape, filters correctly,
and always carries source_url + source_name for citation.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agents.tools.schedule import (
    _tool_get_deworming_schedule,
    _tool_get_vaccine_schedule,
    get_deworming_schedule,
    get_vaccine_schedule,
)


_CREATE_VACCINE = """
CREATE TABLE vaccine_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    species VARCHAR(10) NOT NULL,
    vaccine_name TEXT NOT NULL,
    core BOOLEAN NOT NULL DEFAULT 0,
    age_weeks_start INTEGER,
    age_weeks_end INTEGER,
    interval_description TEXT,
    notes TEXT,
    source_url TEXT NOT NULL,
    source_name TEXT
)
"""

_CREATE_DEWORMING = """
CREATE TABLE deworming_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    species VARCHAR(10) NOT NULL,
    parasite_category VARCHAR(20) NOT NULL,
    life_stage VARCHAR(20) NOT NULL,
    interval_description TEXT,
    notes TEXT,
    source_url TEXT NOT NULL,
    source_name TEXT
)
"""


async def _make_db() -> tuple[AsyncSession, object]:
    """Create an in-memory SQLite DB, seed rows, return (session, engine).

    Caller must dispose the engine when done. Using a helper rather than a
    pytest fixture avoids the async-fixture plugin issue under this repo's
    current pytest config.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.exec_driver_sql(_CREATE_VACCINE)
        await conn.exec_driver_sql(_CREATE_DEWORMING)

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    await session.execute(
        text(
            "INSERT INTO vaccine_schedule "
            "(species, vaccine_name, core, age_weeks_start, age_weeks_end, "
            "interval_description, notes, source_url, source_name) VALUES "
            "('dog', 'DHPP', 1, 6, 16, 'every 2-4 weeks until 16 weeks', 'core', "
            "'https://www.aaha.org/resources/2022-aaha-canine-vaccination-guidelines/', "
            "'AAHA 2022'),"
            "('dog', 'Rabies', 1, 12, 16, 'single dose then 1y/3y', 'core', "
            "'https://www.aaha.org/resources/2022-aaha-canine-vaccination-guidelines/', "
            "'AAHA 2022'),"
            "('cat', 'FVRCP', 1, 6, 16, 'every 3-4 weeks until 16 weeks', 'core', "
            "'https://catvets.com/guidelines/practice-guidelines/aafp-aaha-feline-vaccination-guidelines', "
            "'AAFP/AAHA Feline')"
        )
    )
    await session.execute(
        text(
            "INSERT INTO deworming_schedule "
            "(species, parasite_category, life_stage, interval_description, notes, "
            "source_url, source_name) VALUES "
            "('dog', 'broad', 'puppy_kitten', 'every 2 weeks from 2-12 wks', 'CAPC', "
            "'https://capcvet.org/guidelines/general-guidelines/', 'CAPC General'),"
            "('dog', 'heartworm', 'adult', 'monthly year-round', 'CAPC', "
            "'https://capcvet.org/guidelines/heartworm/', 'CAPC Heartworm')"
        )
    )
    await session.commit()
    return session, engine


@pytest.mark.asyncio
async def test_get_vaccine_schedule_by_species():
    db, engine = await _make_db()
    try:
        rows = await get_vaccine_schedule("dog", db=db)
        assert len(rows) == 2
        names = {r["vaccine_name"] for r in rows}
        assert names == {"DHPP", "Rabies"}
        for r in rows:
            assert r["source_url"].startswith("http")
            assert r["source_name"]
            # Explicitly: no dosage leaked
            assert "dose" not in r
            assert "dosage" not in r
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_vaccine_schedule_age_filter():
    db, engine = await _make_db()
    try:
        # 8-week puppy — both DHPP (6-16) and Rabies (12-16) still relevant
        rows = await get_vaccine_schedule("dog", age_weeks=8, db=db)
        assert len(rows) == 2
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_vaccine_schedule_species_filter():
    db, engine = await _make_db()
    try:
        rows = await get_vaccine_schedule("cat", db=db)
        assert len(rows) == 1
        assert rows[0]["vaccine_name"] == "FVRCP"
        assert rows[0]["source_url"]
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_vaccine_schedule_rejects_bad_species():
    db, engine = await _make_db()
    try:
        assert await get_vaccine_schedule("ferret", db=db) == []
        assert await get_vaccine_schedule("", db=db) == []
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_deworming_schedule_by_species():
    db, engine = await _make_db()
    try:
        rows = await get_deworming_schedule("dog", db=db)
        assert len(rows) == 2
        for r in rows:
            assert r["source_url"].startswith("http")
            assert r["source_name"]
            assert "dose" not in r
            assert "dosage" not in r
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_deworming_schedule_life_stage_filter():
    db, engine = await _make_db()
    try:
        rows = await get_deworming_schedule("dog", life_stage="adult", db=db)
        assert len(rows) == 1
        assert rows[0]["parasite_category"] == "heartworm"
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_tool_wrapper_vaccine():
    db, engine = await _make_db()
    try:
        result = await _tool_get_vaccine_schedule(
            {"species": "dog", "age_weeks": 10}, db, uuid.uuid4()
        )
        assert result["success"] is True
        assert isinstance(result["results"], list)
        assert all("source_url" in r for r in result["results"])
        assert "disclaimer" in result
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_tool_wrapper_deworming():
    db, engine = await _make_db()
    try:
        result = await _tool_get_deworming_schedule(
            {"species": "dog", "life_stage": "puppy_kitten"}, db, uuid.uuid4()
        )
        assert result["success"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["source_name"] == "CAPC General"
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_tool_registered():
    """Ensure the tools are in the registry so the orchestrator can dispatch them."""
    # Trigger registration
    import app.agents.tools.schedule  # noqa: F401
    from app.agents.tools.registry import get_registered_tools

    reg = get_registered_tools()
    assert "get_vaccine_schedule" in reg
    assert "get_deworming_schedule" in reg
