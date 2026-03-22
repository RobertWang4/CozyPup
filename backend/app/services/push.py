"""APNs push notification service with simulated fallback."""

import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# Try to import aioapns; fall back to simulation if unavailable or unconfigured
_apns_client = None
_simulated = True

try:
    from aioapns import APNs, NotificationRequest, PushType

    key_path = Path(settings.apns_key_path) if settings.apns_key_path else None
    if key_path and key_path.exists() and settings.apns_key_id and settings.apns_team_id:
        _apns_client = APNs(
            key=str(key_path),
            key_id=settings.apns_key_id,
            team_id=settings.apns_team_id,
            topic=settings.apns_bundle_id,
            use_sandbox=settings.apns_use_sandbox,
        )
        _simulated = False
        logger.info("apns_initialized", extra={"sandbox": settings.apns_use_sandbox})
    else:
        logger.info("apns_simulated", extra={"reason": "missing key/config"})
except ImportError:
    logger.info("apns_simulated", extra={"reason": "aioapns not installed"})


async def send_push(
    device_token: str,
    title: str,
    body: str,
    data: dict | None = None,
) -> bool:
    """Send a push notification to a single device.

    Returns True if sent (or simulated) successfully, False on failure.
    """
    if _simulated:
        logger.info(
            "push_simulated",
            extra={
                "device_token": device_token[:16] + "...",
                "title": title,
                "body": body[:100],
            },
        )
        return True

    payload = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
            "badge": 1,
        },
    }
    if data:
        payload["custom"] = data

    request = NotificationRequest(
        device_token=device_token,
        message=payload,
        push_type=PushType.ALERT,
    )

    try:
        response = await _apns_client.send_notification(request)
        if not response.is_successful:
            logger.warning(
                "push_failed",
                extra={
                    "device_token": device_token[:16] + "...",
                    "reason": response.description,
                },
            )
            return False
        logger.info("push_sent", extra={"device_token": device_token[:16] + "..."})
        return True
    except Exception as e:
        logger.error(
            "push_error",
            extra={"device_token": device_token[:16] + "...", "error": str(e)[:200]},
        )
        return False


def is_simulated() -> bool:
    """Check if push service is running in simulated mode."""
    return _simulated
