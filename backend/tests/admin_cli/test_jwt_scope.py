"""Tests for JWT scope field on access tokens."""
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from app.auth import create_access_token, verify_token
from app.config import settings


def test_default_scope_is_user():
    token = create_access_token("11111111-1111-1111-1111-111111111111")
    payload = verify_token(token, "access")
    assert payload["scope"] == "user"


def test_admin_scope_round_trip():
    token = create_access_token(
        "22222222-2222-2222-2222-222222222222", scope="admin", ttl_minutes=30
    )
    payload = verify_token(token, "access")
    assert payload["scope"] == "admin"
    assert payload["sub"] == "22222222-2222-2222-2222-222222222222"


def test_expired_admin_token_rejected():
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = pyjwt.encode(
        {"sub": "x", "type": "access", "scope": "admin", "iat": past - timedelta(minutes=5), "exp": past},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        verify_token(expired, "access")
    assert exc.value.status_code == 401
