"""Unified pet ownership check — supports both owners and co-owners.

Every pet-scoped tool must verify access through `can_access_pet` before
mutating or reading pet data. The co-owner join makes pet sharing work:
a user granted access via PetCoOwner can access the pet even though
Pet.user_id points at the primary owner.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Pet, PetCoOwner


async def can_access_pet(
    db: AsyncSession, pet_id: str, user_id: uuid.UUID
) -> Pet | None:
    """Check if user owns or co-owns the pet. Returns Pet or None."""
    pid = uuid.UUID(pet_id)
    # Check direct ownership
    result = await db.execute(
        select(Pet).where(Pet.id == pid, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if pet:
        return pet

    # Check co-ownership
    co_result = await db.execute(
        select(Pet)
        .join(PetCoOwner, PetCoOwner.pet_id == Pet.id)
        .where(Pet.id == pid, PetCoOwner.user_id == user_id)
    )
    return co_result.scalar_one_or_none()


async def get_user_pets(db: AsyncSession, user_id: uuid.UUID) -> list[Pet]:
    """Get all pets a user owns or co-owns, ordered by created_at."""
    owned_q = await db.execute(
        select(Pet).where(Pet.user_id == user_id).order_by(Pet.created_at)
    )
    owned = list(owned_q.scalars().all())

    co_q = await db.execute(
        select(Pet)
        .join(PetCoOwner, PetCoOwner.pet_id == Pet.id)
        .where(PetCoOwner.user_id == user_id)
        .order_by(Pet.created_at)
    )
    co_owned = list(co_q.scalars().all())

    seen = {p.id for p in owned}
    for p in co_owned:
        if p.id not in seen:
            owned.append(p)
            seen.add(p.id)

    return owned
