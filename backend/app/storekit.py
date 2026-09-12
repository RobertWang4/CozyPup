"""StoreKit 2 signed transaction verification.

Wraps Apple's app-store-server-library SignedDataVerifier. The iOS client sends
the raw JWS string from `VerificationResult.jwsRepresentation`. We verify the
JWS chain against Apple's root CAs and only trust the decoded payload.

The environment is decided *server-side* (`allowed_environments`), never by the
client: a production deployment accepts Production transactions only, so a
sandbox JWS can't be used to activate a real subscription. The library already
rejects a payload whose `environment` claim doesn't match the verifier's, so
picking the verifier is the whole check.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.signed_data_verifier import (
    SignedDataVerifier,
    VerificationException,
)

from app.config import settings

logger = logging.getLogger(__name__)

_CERT_DIR = Path(__file__).parent / "certs"
_ROOT_CERT_FILES = ["AppleRootCA-G3.cer", "AppleRootCA-G2.cer"]


def _load_root_certs() -> list[bytes]:
    certs = []
    for name in _ROOT_CERT_FILES:
        path = _CERT_DIR / name
        if path.exists():
            certs.append(path.read_bytes())
        else:
            logger.warning("apple_root_cert_missing", extra={"path": str(path)})
    if not certs:
        raise RuntimeError(
            f"No Apple root certificates found in {_CERT_DIR}. "
            "Download from https://www.apple.com/certificateauthority/"
        )
    return certs


@lru_cache(maxsize=2)
def _verifier_for(environment: Environment) -> SignedDataVerifier:
    return SignedDataVerifier(
        root_certificates=_load_root_certs(),
        # OCSP revocation checks. Verification runs in a worker thread
        # (see routers/subscription.py) so the blocking HTTP call never
        # stalls the event loop.
        enable_online_checks=True,
        environment=environment,
        bundle_id=settings.apple_bundle_id,
        app_apple_id=settings.app_apple_id,
    )


def allowed_environments(*, is_tester: bool = False) -> tuple[Environment, ...]:
    """Environments this server will accept a transaction from.

    Production is always accepted. Sandbox is accepted only off production
    (dev / staging) or for a flagged tester account, so a Sandbox JWS can
    never activate a subscription for an ordinary production user.
    """
    if settings.environment != "production" or is_tester:
        return (Environment.PRODUCTION, Environment.SANDBOX)
    return (Environment.PRODUCTION,)


def verify_signed_transaction(signed_payload: str, *, is_tester: bool = False):
    """Verify a JWS signedTransaction from StoreKit 2.

    Returns the decoded JWSTransactionDecodedPayload on success.
    Raises VerificationException if the signature, chain, bundle id or
    environment is not acceptable.
    """
    return _verify(
        signed_payload,
        is_tester=is_tester,
        decode=lambda v, p: v.verify_and_decode_signed_transaction(p),
        what="transaction",
    )


def verify_notification(signed_payload: str):
    """Verify a signedPayload from an App Store Server Notification V2.

    Returns the decoded ResponseBodyV2DecodedPayload on success. Same
    server-side environment policy as `verify_signed_transaction` — Apple
    sends sandbox notifications to the same URL, and a production server
    should ignore them rather than mutate real subscriptions.
    """
    return _verify(
        signed_payload,
        is_tester=False,
        decode=lambda v, p: v.verify_and_decode_notification(p),
        what="notification",
    )


def _verify(signed_payload: str, *, is_tester: bool, decode, what: str):
    envs = allowed_environments(is_tester=is_tester)
    last: VerificationException | None = None
    for env in envs:
        try:
            return decode(_verifier_for(env), signed_payload)
        except VerificationException as exc:
            last = exc
    logger.warning(
        "storekit_verify_rejected",
        extra={
            "kind": what,
            "allowed_environments": [e.value for e in envs],
            "reason": str(last),
        },
    )
    raise last
