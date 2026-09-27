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


@pytest.mark.asyncio
async def test_chat_pet_snapshot_includes_co_owned_pets(db):
    """A co-owner's chat must see the shared pet, exactly like GET /pets."""
    from app.models import PetCoOwner
    from app.routers.chat import _get_pets

    owner_id = uuid.uuid4()
    db.add(User(id=owner_id, email="owner@example.com", auth_provider="dev"))
    pet = Pet(id=uuid.uuid4(), user_id=owner_id, name="小维", species=Species.dog, color_hex="E8835C")
    db.add(pet)
    await db.flush()
    db.add(PetCoOwner(pet_id=pet.id, user_id=USER_ID))
    await db.flush()

    names = [p.name for p in await _get_pets(db, USER_ID)]
    assert names == ["小维"]


@pytest.mark.asyncio
async def test_co_owner_can_record_events_but_not_delete_pet(db):
    """Tools honour co-ownership for writes on the shared pet; deleting stays owner-only."""
    from app.agents.tools.calendar import create_calendar_event
    from app.agents.tools.pets import delete_pet
    from app.models import PetCoOwner

    owner_id = uuid.uuid4()
    db.add(User(id=owner_id, email="owner2@example.com", auth_provider="dev"))
    pet = Pet(id=uuid.uuid4(), user_id=owner_id, name="小维", species=Species.dog, color_hex="E8835C")
    db.add(pet)
    await db.flush()
    db.add(PetCoOwner(pet_id=pet.id, user_id=USER_ID))
    await db.flush()

    created = await create_calendar_event(
        {"pet_id": str(pet.id), "event_date": "2026-09-27", "title": "下午散步", "category": "daily"},
        db, USER_ID,
    )
    assert created.get("success") is True, created

    updated = await update_pet_profile(
        {"pet_id": str(pet.id), "info": {"weight_kg": 11}, "_force_lock": True}, db, USER_ID,
    )
    assert updated.get("success") is True, updated
    assert pet.weight == 11.0

    deleted = await delete_pet({"pet_id": str(pet.id)}, db, USER_ID)
    assert deleted.get("success") is not True, deleted
