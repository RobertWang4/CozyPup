"""After the user taps "confirm", update_pet_profile runs with _force_lock=True.
That path used to write only the profile JSON, so column fields (weight,
birthday) silently stayed NULL even though the card said "saved"."""
import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agents.tools.pets import apply_profile_updates, update_pet_profile
from app.database import Base
from app.models import Pet, Species, User

USER_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(User(id=USER_ID, email="u@example.com", auth_provider="dev"))
        await session.flush()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_confirmed_update_persists_column_fields(db):
    pet = Pet(id=uuid.uuid4(), user_id=USER_ID, name="小维", species=Species.dog, color_hex="E8835C")
    db.add(pet)
    await db.flush()

    result = await update_pet_profile(
        {"pet_id": str(pet.id), "info": {"weight_kg": 30, "birthday": "2023-03"}, "_force_lock": True},
        db, USER_ID,
    )

    assert result["success"] is True
    assert pet.weight == 30.0
    assert pet.birthday == date(2023, 3, 1)


def test_apply_profile_updates_accepts_month_only_birthday():
    class P:  # minimal stand-in for the ORM row
        birthday = None
        weight = None

    p = P()
    apply_profile_updates(p, {"birthday": "2023-03", "weight": 12.5}, {})
    assert p.birthday == date(2023, 3, 1)
    assert p.weight == 12.5
