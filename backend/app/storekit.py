"""StoreKit 2 signed transaction verification.

Wraps Apple's app-store-server-library SignedDataVerifier. The iOS client sends
the raw JWS string from `VerificationResult.jwsRepresentation`. We verify the
JWS chain against Apple's root CAs and only trust the decoded payload.
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
        enable_online_checks=False,  # online OCSP is slow; chain cert validation is sufficient
        environment=environment,
        bundle_id=settings.apple_bundle_id,
        app_apple_id=settings.app_apple_id,
    )


def verify_signed_transaction(signed_payload: str, sandbox: bool | None = None):
    """Verify a JWS signedTransaction from StoreKit 2.

    Returns the decoded JWSTransactionDecodedPayload on success.
    Raises VerificationException if the signature or chain is invalid.
    """
    env = Environment.SANDBOX if (settings.iap_sandbox if sandbox is None else sandbox) else Environment.PRODUCTION
    verifier = _verifier_for(env)
    try:
        return verifier.verify_and_decode_signed_transaction(signed_payload)
    except VerificationException:
        # If we guessed wrong on the environment, try the other one. Sandbox and
        # production transactions are signed by different intermediates in the
        # test fixtures historically, so falling back is safe.
        other = Environment.PRODUCTION if env == Environment.SANDBOX else Environment.SANDBOX
        logger.info("storekit_env_fallback", extra={"from": env.value, "to": other.value})
        return _verifier_for(other).verify_and_decode_signed_transaction(signed_payload)
