"""DB-backed store for pending user-confirmable actions."""
import uuid as _uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PendingAction

_MAX_AGE = timedelta(hours=1)


async def store_action(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    tool_name: str,
    arguments: dict,
    description: str,
) -> str:
    """Store a pending action and return its ID."""
    action_id = _uuid.uuid4()
    action = PendingAction(
        id=action_id,
        user_id=_uuid.UUID(user_id),
        session_id=_uuid.UUID(session_id),
        tool_name=tool_name,
        arguments=arguments,
        description=description,
    )
    db.add(action)
    await db.flush()
    return str(action_id)


async def pop_action(
    db: AsyncSession,
    action_id: str,
    user_id: str,
) -> PendingAction | None:
    """Pop a pending action if it belongs to the user."""
    cutoff = datetime.now(timezone.utc) - _MAX_AGE
    result = await db.execute(
        select(PendingAction).where(
            PendingAction.id == _uuid.UUID(action_id),
            PendingAction.user_id == _uuid.UUID(user_id),
            PendingAction.created_at > cutoff,
        )
    )
    action = result.scalar_one_or_none()
    if action:
        await db.delete(action)
        await db.flush()
    return action
