import uuid
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.debug.correlation import set_user_id

security = HTTPBearer()

# ---------- JWT ----------


def create_access_token(
    user_id: str,
    *,
    scope: str = "user",
    ttl_minutes: int | None = None,
) -> str:
    ttl = ttl_minutes if ttl_minutes is not None else settings.jwt_access_expire_minutes
    payload = {
        "sub": user_id,
        "type": "access",
        "scope": scope,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ttl),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expire_days),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")

    payload.setdefault("scope", "user")
    return payload


# ---------- OAuth verification ----------

# Cache Apple public keys
_apple_keys_cache: dict | None = None


async def _get_apple_public_keys() -> dict:
    global _apple_keys_cache
    if _apple_keys_cache is None:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://appleid.apple.com/auth/keys")
            resp.raise_for_status()
            _apple_keys_cache = resp.json()
    return _apple_keys_cache


async def verify_apple_token(id_token: str) -> dict:
    """Verify Apple ID token and return {email, name}."""
    keys = await _get_apple_public_keys()
    header = jwt.get_unverified_header(id_token)

    # Find the matching key
    key_data = None
    for k in keys.get("keys", []):
        if k["kid"] == header.get("kid"):
            key_data = k
            break

    if not key_data:
        # Key not found — refresh cache once and retry
        global _apple_keys_cache
        _apple_keys_cache = None
        keys = await _get_apple_public_keys()
        for k in keys.get("keys", []):
            if k["kid"] == header.get("kid"):
                key_data = k
                break

    if not key_data:
        raise HTTPException(status_code=401, detail="Apple token: key not found")

    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
    try:
        payload = jwt.decode(
            id_token,
            public_key,
            algorithms=["RS256"],
            audience=settings.apple_bundle_id,
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Apple token invalid: {e}")

    return {
        "email": payload.get("email", ""),
        "name": payload.get("name"),
    }


_google_keys_cache: dict | None = None


async def _get_google_public_keys() -> dict:
    global _google_keys_cache
    if _google_keys_cache is None:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://www.googleapis.com/oauth2/v3/certs")
            resp.raise_for_status()
            _google_keys_cache = resp.json()
    return _google_keys_cache


async def verify_google_token(id_token: str) -> dict:
    """Verify Google ID token locally via JWKS and return {email, name}."""
    keys = await _get_google_public_keys()
    header = jwt.get_unverified_header(id_token)

    key_data = None
    for k in keys.get("keys", []):
        if k["kid"] == header.get("kid"):
            key_data = k
            break

    if not key_data:
        # Key not found — refresh cache once and retry
        global _google_keys_cache
        _google_keys_cache = None
        keys = await _get_google_public_keys()
        for k in keys.get("keys", []):
            if k["kid"] == header.get("kid"):
                key_data = k
                break

    if not key_data:
        raise HTTPException(status_code=401, detail="Google token: key not found")

    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
    try:
        payload = jwt.decode(
            id_token,
            public_key,
            algorithms=["RS256"],
            audience=settings.google_client_id,
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Google token invalid: {e}")

    return {
        "email": payload.get("email", ""),
        "name": payload.get("name"),
        "picture": payload.get("picture"),
    }


async def verify_token_with_revocation(token: str, expected_type: str, db) -> dict:
    """verify_token + revocation check. Returns payload or raises 401."""
    from sqlalchemy import select
    from app.models import TokenRevocation

    payload = verify_token(token, expected_type)
    uid = payload.get("sub")
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing sub")

    try:
        uid_uuid = uuid.UUID(uid)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid sub")

    row = await db.execute(select(TokenRevocation).where(TokenRevocation.user_id == uid_uuid))
    revocation = row.scalar_one_or_none()
    if revocation is not None:
        iat = payload.get("iat")
        if iat is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")
        from datetime import datetime, timezone
        iat_dt = datetime.fromtimestamp(iat, tz=timezone.utc) if isinstance(iat, (int, float)) else iat
        if iat_dt.tzinfo is None:
            iat_dt = iat_dt.replace(tzinfo=timezone.utc)
        revoked_at = revocation.revoked_at
        if revoked_at.tzinfo is None:
            revoked_at = revoked_at.replace(tzinfo=timezone.utc)
        if iat_dt < revoked_at:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    return payload


# ---------- FastAPI dependency ----------


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    from sqlalchemy import select
    from app.models import User

    payload = await verify_token_with_revocation(credentials.credentials, "access", db)
    uid = uuid.UUID(payload["sub"])
    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    now = datetime.now(timezone.utc)
    if user.deleted_at is not None and user.deleted_at <= now:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deleted")
    if user.banned_until is not None and user.banned_until > now:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account banned")
    set_user_id(str(uid))
    return uid
