"""Admin auth endpoints: dev-login (dev only), OAuth loopback, whoami."""
from __future__ import annotations

import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, verify_google_token
from app.config import settings
from app.database import get_db
from app.models import User

from .deps import AdminContext, require_admin

admin_auth_router = APIRouter(prefix="/auth", tags=["admin-auth"])

ADMIN_TOKEN_TTL_MINUTES = 120

# In-memory OAuth state: {state: {"callback": url, "ts": epoch}}. Server-instance
# local is fine because the CLI hits the same instance within seconds.
_oauth_states: dict[str, dict] = {}
_OAUTH_STATE_TTL_SECONDS = 300


class DevLoginBody(BaseModel):
    email: str   # Use plain str (no email-validator dep). Validation done by lookup.


def _dev_env_check():
    env = (getattr(settings, "environment", None) or "").lower()
    if env != "dev":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _issue_admin_token(user: User) -> dict:
    token = create_access_token(str(user.id), scope="admin", ttl_minutes=ADMIN_TOKEN_TTL_MINUTES)
    return {
        "token": token,
        "scope": "admin",
        "expires_in": ADMIN_TOKEN_TTL_MINUTES * 60,
        "email": user.email,
    }


@admin_auth_router.post("/dev-login")
async def dev_login(body: DevLoginBody, db: AsyncSession = Depends(get_db)):
    _dev_env_check()
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if user is None or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return {"data": _issue_admin_token(user), "audit_id": None, "env": getattr(settings, "environment", "unknown")}


@admin_auth_router.get("/oauth/start")
async def oauth_start(callback: str, request: Request):
    """Begin OAuth loopback flow."""
    if not callback.startswith("http://127.0.0.1:") and not callback.startswith("http://localhost:"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="callback must be loopback")

    state = secrets.token_urlsafe(32)
    _oauth_states[state] = {"callback": callback, "ts": time.time()}

    google_client_id = getattr(settings, "google_client_id", None)
    if not google_client_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="google oauth not configured")

    redirect_uri = f"{request.base_url}api/v1/admin/auth/oauth/finish"
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={google_client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        "&scope=openid%20email%20profile"
        f"&state={state}"
    )
    return RedirectResponse(auth_url, status_code=302)


@admin_auth_router.get("/oauth/finish")
async def oauth_finish(
    code: str,
    state: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    entry = _oauth_states.pop(state, None)
    if entry is None or (time.time() - entry["ts"]) > _OAUTH_STATE_TTL_SECONDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid or expired state")

    import httpx
    redirect_uri = f"{request.base_url}api/v1/admin/auth/oauth/finish"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": getattr(settings, "google_client_secret", ""),
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token exchange failed")
    tok = resp.json()
    id_token = tok.get("id_token")
    if not id_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing id_token")

    profile = await verify_google_token(id_token)
    user = (await db.execute(select(User).where(User.email == profile["email"]))).scalar_one_or_none()
    if user is None or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    issued = _issue_admin_token(user)
    callback = entry["callback"]
    sep = "&" if "?" in callback else "?"
    return RedirectResponse(
        f"{callback}{sep}token={issued['token']}&expires_in={issued['expires_in']}&email={issued['email']}",
        status_code=302,
    )


@admin_auth_router.get("/whoami")
async def whoami(ctx: AdminContext = Depends(require_admin)):
    return {
        "data": {"email": ctx.user.email, "scope": ctx.scope, "user_id": str(ctx.user.id)},
        "audit_id": None,
        "env": getattr(settings, "environment", "unknown"),
    }
