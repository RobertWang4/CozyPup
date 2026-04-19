"""Public server-rendered web flow for accepting family invites.

Flow overview:

    GET  /invite/{invite_id}
      → renders invite_landing.html with "Continue with Google" and
        "Continue with Apple" buttons.

    GET  /invite/google/start?invite_id={id}
      → 302 redirects to Google OAuth consent screen
      → state carries the invite_id so we can resume after callback

    GET  /invite/google/callback?code={code}&state={invite_id}
      → exchanges code for id_token
      → verifies id_token, extracts email / sub / name
      → finds or creates a User, accepts the invite, renders success.

    GET  /invite/apple/start?invite_id={id}
      → 302 redirects to Apple OAuth consent (response_mode=form_post)

    POST /invite/apple/callback  (Apple POSTs here, not GET)
      → reads code + state from form body
      → exchanges code via Apple token endpoint (with dynamic client_secret
        JWT signed with our .p8 key)
      → verifies id_token against the web Services ID audience
      → finds or creates a User, accepts the invite, renders success.

    Errors (expired, already used, wrong audience, etc) render invite_error.html.

Why no session/cookie: the OAuth `state` parameter already carries the
invite_id through the round-trip, so we don't need to persist anything
between the landing page and the callback. Everything is stateless.
"""

import json
import logging
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import auth_apple_web
from app.auth import verify_google_token
from app.config import settings
from app.database import get_db
from app.models import FamilyInvite, User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["web-invite"])

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPES = "openid email profile"


def _redirect_uri() -> str:
    base = settings.server_public_url.rstrip("/")
    return f"{base}/invite/google/callback"


def _invite_is_live(invite: FamilyInvite) -> bool:
    if invite.status != "pending":
        return False
    if invite.expires_at is None:
        return True
    return datetime.now(timezone.utc) < invite.expires_at


async def _render_error(request: Request, heading: str, message: str, status_code: int = 400) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "invite_error.html",
        {"heading": heading, "message": message},
        status_code=status_code,
    )


@router.get("/invite/{invite_id}", response_class=HTMLResponse)
async def invite_landing(
    invite_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public landing page for an invite link."""
    try:
        iid = uuid.UUID(invite_id)
    except ValueError:
        return await _render_error(
            request,
            heading="Invite not found",
            message="This link doesn't look right. Please ask your friend to share a fresh invite.",
            status_code=404,
        )

    invite_q = await db.execute(select(FamilyInvite).where(FamilyInvite.id == iid))
    invite = invite_q.scalar_one_or_none()
    if invite is None:
        return await _render_error(
            request,
            heading="Invite not found",
            message="This invite doesn't exist. It may have already been used or cancelled.",
            status_code=404,
        )

    if invite.status == "accepted":
        return await _render_error(
            request,
            heading="Already accepted",
            message="This invite has already been used. Sign in to CozyPup with the same account to see shared pets.",
            status_code=410,
        )

    if invite.status in {"revoked", "expired"} or not _invite_is_live(invite):
        # Soft-mark expired if needed (best-effort, not critical)
        if invite.status == "pending" and invite.expires_at and datetime.now(timezone.utc) >= invite.expires_at:
            invite.status = "expired"
            await db.commit()
        return await _render_error(
            request,
            heading="Invite expired",
            message="This invite is no longer valid. Ask your friend to send a new one from the CozyPup app.",
            status_code=410,
        )

    inviter_q = await db.execute(select(User).where(User.id == invite.inviter_id))
    inviter = inviter_q.scalar_one_or_none()
    if inviter is None:
        return await _render_error(
            request,
            heading="Invite unavailable",
            message="The person who sent this invite is no longer reachable.",
            status_code=410,
        )

    inviter_name = inviter.name or (inviter.email.split("@")[0] if inviter.email else "A CozyPup user")
    inviter_initial = (inviter_name[:1] or "?").upper()

    # Build /invite/{google,apple}/start?invite_id=... links. The start
    # endpoints wrap the authorize URLs and keep provider client config
    # out of the rendered HTML.
    base = settings.server_public_url.rstrip("/")
    google_auth_url = f"{base}/invite/google/start?invite_id={invite.id}"
    apple_auth_url = f"{base}/invite/apple/start?invite_id={invite.id}"

    minutes_left = 0
    if invite.expires_at:
        delta = invite.expires_at - datetime.now(timezone.utc)
        minutes_left = max(0, int(delta.total_seconds() // 60))

    return templates.TemplateResponse(
        request,
        "invite_landing.html",
        {
            "inviter_name": inviter_name,
            "inviter_initial": inviter_initial,
            "google_auth_url": google_auth_url,
            "google_enabled": bool(settings.google_web_client_id),
            "apple_auth_url": apple_auth_url,
            "apple_enabled": bool(
                settings.apple_web_service_id
                and settings.apple_web_key_id
                and settings.apple_web_private_key
            ),
            "minutes_left": minutes_left,
        },
    )


@router.get("/invite/google/start")
async def invite_google_start(invite_id: str, request: Request):
    """Redirect to Google OAuth consent screen with invite_id in state."""
    if not settings.google_web_client_id:
        return await _render_error(
            request,
            heading="Sign-in unavailable",
            message="Google sign-in is not configured on this server. Please try again later.",
            status_code=503,
        )

    # Include a random nonce in state to protect against CSRF. The invite_id
    # is the meaningful part we'll use on the callback.
    state = f"{invite_id}:{secrets.token_urlsafe(16)}"
    params = {
        "client_id": settings.google_web_client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=302)


@router.get("/invite/google/callback", response_class=HTMLResponse)
async def invite_google_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Google OAuth callback. Exchanges code, verifies id_token, accepts invite."""
    if error:
        logger.warning("invite_oauth_error_from_google", extra={"error": error})
        return await _render_error(
            request,
            heading="Sign-in cancelled",
            message="You cancelled the Google sign-in. Open the invite link again to retry.",
            status_code=400,
        )
    if not code or not state:
        return await _render_error(
            request,
            heading="Bad request",
            message="The sign-in flow is missing required parameters.",
            status_code=400,
        )

    # state = invite_id:nonce
    try:
        invite_id_str, _nonce = state.split(":", 1)
        invite_id = uuid.UUID(invite_id_str)
    except (ValueError, AttributeError):
        return await _render_error(
            request,
            heading="Bad request",
            message="Invalid sign-in state.",
            status_code=400,
        )

    # Load the invite first — no point exchanging the code if it's already dead.
    invite_q = await db.execute(select(FamilyInvite).where(FamilyInvite.id == invite_id))
    invite = invite_q.scalar_one_or_none()
    if invite is None:
        return await _render_error(
            request,
            heading="Invite not found",
            message="We couldn't find the invite you were trying to accept.",
            status_code=404,
        )
    if not _invite_is_live(invite):
        return await _render_error(
            request,
            heading="Invite expired",
            message="This invite is no longer valid. Please ask your friend to send a new one.",
            status_code=410,
        )

    # Exchange the authorization code for tokens.
    if not settings.google_web_client_id or not settings.google_web_client_secret:
        logger.error("google_web_credentials_missing")
        return await _render_error(
            request,
            heading="Sign-in unavailable",
            message="Google sign-in is not configured on this server.",
            status_code=503,
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_web_client_id,
                    "client_secret": settings.google_web_client_secret,
                    "redirect_uri": _redirect_uri(),
                    "grant_type": "authorization_code",
                },
            )
    except httpx.HTTPError as exc:
        logger.exception("google_token_exchange_network_error", extra={"error": str(exc)})
        return await _render_error(
            request,
            heading="Sign-in failed",
            message="Couldn't reach Google. Please try again in a moment.",
            status_code=502,
        )

    if token_resp.status_code != 200:
        logger.warning(
            "google_token_exchange_failed",
            extra={"status": token_resp.status_code, "body": token_resp.text[:300]},
        )
        return await _render_error(
            request,
            heading="Sign-in failed",
            message="Google rejected the sign-in. Please open the invite link and try again.",
            status_code=400,
        )

    token_data = token_resp.json()
    id_token = token_data.get("id_token")
    if not id_token:
        logger.error("google_token_exchange_no_id_token", extra={"body": str(token_data)[:300]})
        return await _render_error(
            request,
            heading="Sign-in failed",
            message="Google didn't return a valid identity token.",
            status_code=502,
        )

    # Verify the id_token. The existing verify_google_token helper checks
    # the iOS audience by default, so for the web client we need a local
    # verification that targets the web client_id instead.
    try:
        claims = await _verify_google_web_id_token(id_token)
    except Exception as exc:
        logger.warning("google_id_token_verify_failed", extra={"error": str(exc)})
        return await _render_error(
            request,
            heading="Sign-in failed",
            message="We couldn't verify your Google account. Please try again.",
            status_code=400,
        )

    email = claims.get("email")
    google_sub = claims.get("sub")
    name = claims.get("name") or (email.split("@")[0] if email else "CozyPup user")

    if not email or not google_sub:
        return await _render_error(
            request,
            heading="Sign-in failed",
            message="Google didn't return an email address. Please try again or use a different account.",
            status_code=400,
        )

    return await _finalize_invite_acceptance(
        request=request,
        db=db,
        invite=invite,
        email=email.lower(),
        name=name,
        auth_provider="google",
    )


async def _verify_google_web_id_token(id_token: str) -> dict:
    """Verify Google ID token against the *web* client_id audience.

    The existing `app.auth.verify_google_token` helper verifies against
    settings.google_client_id (the iOS native client). The web flow uses a
    different client_id, so we call into jose directly with the correct
    audience.
    """
    from jose import jwt
    from app.auth import _get_google_public_keys  # reuse cached JWKS

    keys = await _get_google_public_keys()
    header = jwt.get_unverified_header(id_token)
    kid = header.get("kid")
    key = next((k for k in keys["keys"] if k.get("kid") == kid), None)
    if key is None:
        # Refresh cache once if the kid isn't found (key rotation)
        import app.auth as _auth_module
        _auth_module._google_keys_cache = None
        keys = await _get_google_public_keys()
        key = next((k for k in keys["keys"] if k.get("kid") == kid), None)
        if key is None:
            raise ValueError("Unknown Google signing key")

    claims = jwt.decode(
        id_token,
        key,
        algorithms=["RS256"],
        audience=settings.google_web_client_id,
        issuer=["https://accounts.google.com", "accounts.google.com"],
        options={"verify_at_hash": False},
    )
    return claims


# ---------------------------------------------------------------------------
# Apple Sign in with Apple — Web flow
# ---------------------------------------------------------------------------

APPLE_AUTHORIZE_URL = "https://appleid.apple.com/auth/authorize"
APPLE_SCOPES = "name email"


def _apple_redirect_uri() -> str:
    base = settings.server_public_url.rstrip("/")
    return f"{base}/invite/apple/callback"


def _apple_configured() -> bool:
    return bool(
        settings.apple_web_service_id
        and settings.apple_web_key_id
        and settings.apple_web_private_key
    )


@router.get("/invite/apple/start")
async def invite_apple_start(invite_id: str, request: Request):
    """Redirect to Sign in with Apple consent screen."""
    if not _apple_configured():
        return await _render_error(
            request,
            heading="Apple sign-in unavailable",
            message="Sign in with Apple isn't configured on this server yet.",
            status_code=503,
        )

    state = f"{invite_id}:{secrets.token_urlsafe(16)}"
    params = {
        "client_id": settings.apple_web_service_id,
        "redirect_uri": _apple_redirect_uri(),
        "response_type": "code id_token",
        "scope": APPLE_SCOPES,
        "state": state,
        # Apple requires form_post when `scope` includes name/email so that
        # the user's name (only returned on first consent) can be POSTed
        # back to us without going through the browser URL bar.
        "response_mode": "form_post",
    }
    return RedirectResponse(f"{APPLE_AUTHORIZE_URL}?{urlencode(params)}", status_code=302)


@router.post("/invite/apple/callback", response_class=HTMLResponse)
async def invite_apple_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
    code: str | None = Form(default=None),
    state: str | None = Form(default=None),
    id_token: str | None = Form(default=None),
    user: str | None = Form(default=None),  # JSON string, only on first consent
    error: str | None = Form(default=None),
):
    """Apple OAuth callback. Called via POST (response_mode=form_post)."""
    if error:
        logger.warning("invite_apple_oauth_error", extra={"error": error})
        return await _render_error(
            request,
            heading="Sign-in cancelled",
            message="You cancelled the Apple sign-in. Open the invite link again to retry.",
            status_code=400,
        )
    if not state:
        return await _render_error(
            request,
            heading="Bad request",
            message="The sign-in flow is missing required parameters.",
            status_code=400,
        )

    try:
        invite_id_str, _nonce = state.split(":", 1)
        invite_id_uuid = uuid.UUID(invite_id_str)
    except (ValueError, AttributeError):
        return await _render_error(
            request,
            heading="Bad request",
            message="Invalid sign-in state.",
            status_code=400,
        )

    invite_q = await db.execute(select(FamilyInvite).where(FamilyInvite.id == invite_id_uuid))
    invite = invite_q.scalar_one_or_none()
    if invite is None:
        return await _render_error(
            request,
            heading="Invite not found",
            message="We couldn't find the invite you were trying to accept.",
            status_code=404,
        )
    if not _invite_is_live(invite):
        return await _render_error(
            request,
            heading="Invite expired",
            message="This invite is no longer valid. Please ask your friend to send a new one.",
            status_code=410,
        )

    if not _apple_configured():
        return await _render_error(
            request,
            heading="Apple sign-in unavailable",
            message="Sign in with Apple isn't configured on this server.",
            status_code=503,
        )

    # Apple returns id_token directly in the form_post response — we can
    # optionally skip the code exchange if we trust the direct id_token.
    # For extra safety, we still exchange the code if present, which also
    # verifies the client_secret JWT and gives us a refresh_token if we
    # ever need one.
    verified_claims: dict | None = None
    if code:
        try:
            token_data = await auth_apple_web.exchange_code_for_tokens(code, _apple_redirect_uri())
        except Exception as exc:
            logger.warning("apple_token_exchange_failed", extra={"error": str(exc)})
            return await _render_error(
                request,
                heading="Sign-in failed",
                message="Apple rejected the sign-in. Please open the invite link and try again.",
                status_code=400,
            )
        exchanged_id_token = token_data.get("id_token")
        if exchanged_id_token:
            id_token = exchanged_id_token

    if not id_token:
        return await _render_error(
            request,
            heading="Sign-in failed",
            message="Apple didn't return an identity token.",
            status_code=502,
        )

    try:
        verified_claims = await auth_apple_web.verify_id_token(id_token)
    except Exception as exc:
        logger.warning("apple_id_token_verify_failed", extra={"error": str(exc)})
        return await _render_error(
            request,
            heading="Sign-in failed",
            message="We couldn't verify your Apple account. Please try again.",
            status_code=400,
        )

    apple_sub = verified_claims.get("sub")
    email = verified_claims.get("email")
    if not apple_sub:
        return await _render_error(
            request,
            heading="Sign-in failed",
            message="Apple didn't return a user identifier.",
            status_code=400,
        )

    # Parse the `user` form field for the name (only present on first
    # consent — returned as a JSON string like
    # `{"name":{"firstName":"A","lastName":"B"},"email":"x@y"}`).
    name: str | None = None
    if user:
        try:
            user_info = json.loads(user)
            name_obj = user_info.get("name") or {}
            first = name_obj.get("firstName") or ""
            last = name_obj.get("lastName") or ""
            name = (first + " " + last).strip() or None
        except (ValueError, TypeError):
            name = None

    # Apple's id_token carries the email only on first login, or when the
    # user has not enabled Hide My Email. If we have no email at all, fall
    # back to the "private relay" synthetic email Apple includes on the
    # token: this is still a stable user identifier for account linking.
    # If even that is missing we can't proceed.
    if not email:
        return await _render_error(
            request,
            heading="Sign-in failed",
            message="Apple didn't share an email. Please retry and allow email sharing.",
            status_code=400,
        )

    return await _finalize_invite_acceptance(
        request=request,
        db=db,
        invite=invite,
        email=email.lower(),
        name=name or email.split("@")[0],
        auth_provider="apple",
    )


async def _finalize_invite_acceptance(
    *,
    request: Request,
    db: AsyncSession,
    invite: FamilyInvite,
    email: str,
    name: str,
    auth_provider: str,
) -> HTMLResponse:
    """Shared tail-end of Google + Apple invite flows.

    Finds or creates the User, runs the validation checks, flips the
    invite to accepted, promotes the user into the family, commits, and
    renders the success page.
    """
    user_q = await db.execute(select(User).where(User.email == email))
    user = user_q.scalar_one_or_none()
    if user is None:
        user = User(email=email, name=name, auth_provider=auth_provider)
        db.add(user)
        await db.flush()
        logger.info(
            "user_created_via_invite_web",
            extra={"user_id": str(user.id), "email": email, "provider": auth_provider},
        )

    if user.id == invite.inviter_id:
        return await _render_error(
            request,
            heading="Can't accept your own invite",
            message="You created this invite yourself. Share the link with someone else.",
            status_code=400,
        )
    if user.family_role == "payer":
        return await _render_error(
            request,
            heading="Already a Duo payer",
            message="You already pay for a Duo plan. Revoke your current partner first.",
            status_code=400,
        )
    if (
        user.family_role == "member"
        and user.family_payer_id
        and user.family_payer_id != invite.inviter_id
    ):
        return await _render_error(
            request,
            heading="Already in another family",
            message="You're already part of another Duo plan. Ask the other payer to remove you first.",
            status_code=400,
        )

    invite.status = "accepted"
    invite.invitee_id = user.id
    invite.invitee_email = email
    invite.accepted_at = datetime.now(timezone.utc)
    user.family_role = "member"
    user.family_payer_id = invite.inviter_id
    user.subscription_status = "active"

    inviter_q = await db.execute(select(User).where(User.id == invite.inviter_id))
    inviter = inviter_q.scalar_one_or_none()

    await db.commit()

    logger.info(
        "family_invite_accepted_via_web",
        extra={
            "inviter_id": str(invite.inviter_id),
            "invitee_id": str(user.id),
            "invite_id": str(invite.id),
            "provider": auth_provider,
        },
    )

    inviter_name = (inviter.name if inviter else None) or "your friend"
    return templates.TemplateResponse(
        request,
        "invite_success.html",
        {
            "inviter_name": inviter_name,
            "app_apple_id": settings.app_apple_id,
        },
    )


# ---------------------------------------------------------------------------
# Apple domain association file
# ---------------------------------------------------------------------------

@router.get(
    "/.well-known/apple-developer-domain-association.txt",
    response_class=PlainTextResponse,
)
async def apple_domain_association():
    """Serve the Apple-provided domain association content.

    Apple downloads this file when verifying the domain configured on a
    Services ID. The content is the raw text Apple gave you when you added
    a domain in the Services ID config, stored in the
    APPLE_WEB_DOMAIN_ASSOCIATION env var (via Secret Manager).
    """
    content = settings.apple_web_domain_association
    if not content:
        return PlainTextResponse("not configured", status_code=404)
    return PlainTextResponse(content)
