"""Background worker that polls reminders and sends push notifications.

Usage:
    python -m app.worker

Polls the reminders table every 60 seconds for due, unsent reminders.
For each, sends a push notification to all of the user's registered devices,
then marks the reminder as sent.
"""

import asyncio
import logging

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import DeviceToken, Pet, Reminder
from app.services.push import is_simulated, send_push

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = 60  # seconds


async def _process_due_reminders():
    """Find and process all due, unsent reminders."""
    async with async_session() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Reminder)
            .where(Reminder.trigger_at <= now, Reminder.sent == False)  # noqa: E712
            .order_by(Reminder.trigger_at)
            .limit(100)
        )
        reminders = result.scalars().all()

        if not reminders:
            return 0

        processed = 0
        for reminder in reminders:
            # Get pet name for the notification
            pet_name = await _get_pet_name(db, reminder.pet_id)

            # Get all device tokens for this user
            tokens = await _get_device_tokens(db, reminder.user_id)

            if not tokens:
                logger.info(
                    "reminder_no_devices",
                    extra={"reminder_id": str(reminder.id), "user_id": str(reminder.user_id)},
                )
                # Mark as sent anyway — no devices to deliver to
                reminder.sent = True
                processed += 1
                continue

            title = f"🐾 {pet_name}" if pet_name else "🐾 CozyPup Reminder"
            body = reminder.title
            if reminder.body:
                body += f" — {reminder.body}"

            # Send to all user devices
            success = False
            for device_token in tokens:
                sent = await send_push(
                    device_token=device_token,
                    title=title,
                    body=body,
                    data={
                        "reminder_id": str(reminder.id),
                        "pet_id": str(reminder.pet_id),
                        "type": reminder.type,
                    },
                )
                if sent:
                    success = True

            if success:
                reminder.sent = True
                processed += 1
                logger.info(
                    "reminder_sent",
                    extra={
                        "reminder_id": str(reminder.id),
                        "type": reminder.type,
                        "title": reminder.title[:100],
                    },
                )
            else:
                logger.warning(
                    "reminder_send_failed",
                    extra={"reminder_id": str(reminder.id)},
                )

        await db.commit()
        return processed


async def _get_pet_name(db: AsyncSession, pet_id) -> str:
    result = await db.execute(select(Pet.name).where(Pet.id == pet_id))
    row = result.scalar_one_or_none()
    return row or ""


async def _get_device_tokens(db: AsyncSession, user_id) -> list[str]:
    result = await db.execute(
        select(DeviceToken.token).where(DeviceToken.user_id == user_id)
    )
    return [row for row in result.scalars().all()]


async def run_worker():
    """Main worker loop."""
    mode = "SIMULATED" if is_simulated() else "LIVE"
    logger.info(f"Push notification worker started ({mode} mode)")
    logger.info(f"Polling every {POLL_INTERVAL}s for due reminders")

    while True:
        try:
            count = await _process_due_reminders()
            if count > 0:
                logger.info(f"Processed {count} reminder(s)")
        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)

        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run_worker())
