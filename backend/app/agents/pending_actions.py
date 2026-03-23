"""In-memory store for pending user-confirmable actions.

When the pre-processor detects an action with medium confidence,
it is stored here and a confirm card is shown to the user.
On confirm, the action is popped and executed directly — no LLM needed.
"""

import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

_MAX_AGE = timedelta(hours=1)


@dataclass
class PendingAction:
    action_id: str
    user_id: str
    session_id: str
    tool_name: str
    arguments: dict
    description: str
    created_at: datetime


_store: dict[str, PendingAction] = {}


def store_action(
    user_id: str,
    session_id: str,
    tool_name: str,
    arguments: dict,
    description: str,
) -> str:
    """Store a pending action and return its ID."""
    _cleanup()
    action_id = str(_uuid.uuid4())
    _store[action_id] = PendingAction(
        action_id=action_id,
        user_id=user_id,
        session_id=session_id,
        tool_name=tool_name,
        arguments=arguments,
        description=description,
        created_at=datetime.utcnow(),
    )
    return action_id


def pop_action(action_id: str, user_id: str) -> PendingAction | None:
    """Pop a pending action if it belongs to the user. Returns None if not found/expired."""
    action = _store.get(action_id)
    if action and action.user_id == user_id:
        del _store[action_id]
        return action
    return None


def _cleanup():
    cutoff = datetime.utcnow() - _MAX_AGE
    expired = [k for k, v in _store.items() if v.created_at < cutoff]
    for k in expired:
        del _store[k]
