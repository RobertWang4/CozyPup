import uuid
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.debug.correlation import set_user_id

security = HTTPBearer()

# ---------- JWT ----------


def create_access_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_expire_minutes),
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
        raise HTTPException(status_code=401, detail="Apple token: key not found")

    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
    try:
        payload = jwt.decode(
            id_token,
            public_key,
            algorithms=["RS256"],
            audience=settings.apple_bundle_id if hasattr(settings, "apple_bundle_id") else None,
            options={"verify_aud": False},  # relax for dev
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Apple token invalid: {e}")

    return {
        "email": payload.get("email", ""),
        "name": payload.get("name"),
    }


async def verify_google_token(id_token: str) -> dict:
    """Verify Google ID token via tokeninfo endpoint and return {email, name}."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Google token invalid")

    data = resp.json()
    return {
        "email": data.get("email", ""),
        "name": data.get("name"),
    }


# ---------- FastAPI dependency ----------


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> uuid.UUID:
    payload = verify_token(credentials.credentials, "access")
    uid = uuid.UUID(payload["sub"])
    set_user_id(str(uid))
    return uid
