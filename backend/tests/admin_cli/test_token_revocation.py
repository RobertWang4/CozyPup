"""verify_token honors token_revocation: rejects tokens whose iat < revoked_at."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest
from fastapi import HTTPException

from app.auth import create_access_token, verify_token_with_revocation


@pytest.mark.asyncio
async def test_token_not_revoked_passes():
    user_id = uuid.uuid4()
    tok = create_access_token(str(user_id))

    db = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = None  # no revocation row
    db.execute.return_value = res

    payload = await verify_token_with_revocation(tok, "access", db)
    assert payload["sub"] == str(user_id)


@pytest.mark.asyncio
async def test_token_issued_before_revocation_rejected():
    user_id = uuid.uuid4()
    tok = create_access_token(str(user_id))

    revocation = MagicMock()
    revocation.revoked_at = datetime.now(timezone.utc) + timedelta(minutes=5)  # future → all existing tokens invalid
    db = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = revocation
    db.execute.return_value = res

    with pytest.raises(HTTPException) as exc:
        await verify_token_with_revocation(tok, "access", db)
    assert exc.value.status_code == 401
