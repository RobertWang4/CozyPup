"""Apple Sign in with Apple — Web flow helpers.

The iOS Sign in with Apple flow (in `auth.py`) uses the Bundle ID as the
client_id / audience. The web flow uses a separate **Services ID** and
requires us to:

1. Generate a short-lived JWT as `client_secret`, signed with a private
   key (.p8) we download from Apple Developer → Keys. The JWT is signed
   with ES256 and has iss=Team ID, sub=Services ID, aud=appleid.

2. Verify the returned id_token using Apple's JWKS endpoint, against an
   audience of the Services ID (not the Bundle ID).

Both steps are encapsulated here to keep `auth.py` (iOS path) untouched.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt

from app.config import settings

logger = logging.getLogger(__name__)

APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"

# The client_secret JWT is good for up to 6 months, but we regenerate a
# fresh one on every callback — 10 minutes is plenty and limits blast
# radius if it ever leaks into logs.
_CLIENT_SECRET_TTL = 600  # seconds

_keys_cache: dict | None = None


def _team_id() -> str:
    """Team ID, falling back to the APNs team id (same Apple Developer team)."""
    return settings.apple_web_team_id or settings.apns_team_id


def client_secret() -> str:
    """Generate a fresh ES256-signed client_secret JWT for Apple's token endpoint."""
    now = int(time.time())
    payload = {
        "iss": _team_id(),
        "iat": now,
        "exp": now + _CLIENT_SECRET_TTL,
        "aud": APPLE_ISSUER,
        "sub": settings.apple_web_service_id,
    }
    headers = {"kid": settings.apple_web_key_id, "alg": "ES256"}
    return jwt.encode(
        payload,
        settings.apple_web_private_key,
        algorithm="ES256",
        headers=headers,
    )


async def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict[str, Any]:
    """Exchange an authorization code for Apple's token response."""
    data = {
        "client_id": settings.apple_web_service_id,
        "client_secret": client_secret(),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            APPLE_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        logger.warning(
            "apple_token_exchange_failed",
            extra={"status": resp.status_code, "body": resp.text[:300]},
        )
        raise ValueError(f"Apple token exchange failed: {resp.status_code}")
    return resp.json()


async def _get_apple_public_keys() -> dict:
    global _keys_cache
    if _keys_cache is None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(APPLE_KEYS_URL)
            resp.raise_for_status()
            _keys_cache = resp.json()
    return _keys_cache


async def verify_id_token(id_token: str) -> dict[str, Any]:
    """Verify an Apple id_token against the web Services ID audience.

    Raises ValueError if the token is invalid.
    """
    keys = await _get_apple_public_keys()
    header = jwt.get_unverified_header(id_token)
    kid = header.get("kid")
    jwk = next((k for k in keys["keys"] if k.get("kid") == kid), None)
    if jwk is None:
        # Refresh the cache once in case of key rotation.
        global _keys_cache
        _keys_cache = None
        keys = await _get_apple_public_keys()
        jwk = next((k for k in keys["keys"] if k.get("kid") == kid), None)
        if jwk is None:
            raise ValueError("Unknown Apple signing key")

    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
    claims = jwt.decode(
        id_token,
        public_key,
        algorithms=["RS256"],
        audience=settings.apple_web_service_id,
        issuer=APPLE_ISSUER,
    )
    return claims
