"""Summary Agent — extracts health events from chat and creates calendar entries."""

import json
import logging
from datetime import date, datetime, timedelta

import litellm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.agents.prompts import SUMMARY_PROMPT
from app.config import settings
from app.models import (
    CalendarEvent,
    Chat,
    EventCategory,
    EventSource,
    EventType,
    Pet,
    Reminder,
)

logger = logging.getLogger(__name__)

REMINDER_CATEGORIES = {"abnormal", "medical"}


class SummaryAgent(BaseAgent):
    name = "summary_agent"

    async def _run(self, message: str, context: dict, **kwargs) -> dict:
        db: AsyncSession = context["db"]
        user_id = context["user_id"]
        session_id = context["session_id"]
        pets: list[Pet] = context["pets"]

        # 1. Fetch all messages from this session
        result = await db.execute(
            select(Chat)
            .where(Chat.session_id == session_id)
            .order_by(Chat.created_at)
        )
        chats = result.scalars().all()

        if not chats:
            return {
                "events_created": 0,
                "reminders_created": 0,
                "summary_text": "No messages found in this session to summarize.",
                "cards": [],
            }

        # 2. Build conversation text and pet context
        conversation_lines = []
        for chat in chats:
            role_label = "User" if chat.role.value == "user" else "Assistant"
            conversation_lines.append(f"{role_label}: {chat.content}")
        conversation_text = "\n".join(conversation_lines)

        pet_profiles = []
        for pet in pets:
            profile = f"- {pet.name} ({pet.species.value}, {pet.breed})"
            if pet.weight:
                profile += f", {pet.weight}kg"
            pet_profiles.append(profile)
        pet_context = "\n".join(pet_profiles) if pet_profiles else "No pets registered."

        today_str = date.today().isoformat()

        llm_messages = [
            {
                "role": "system",
                "content": SUMMARY_PROMPT.format(
                    today_date=today_str,
                    pet_profiles=pet_context,
                ),
            },
            {"role": "user", "content": conversation_text},
        ]

        # 3. Call LiteLLM (non-streaming)
        try:
            response = await litellm.acompletion(
                model=settings.cheap_model,
                messages=llm_messages,
                temperature=0,
                max_tokens=2000,
            )
            raw = response.choices[0].message.content.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                lines = raw.split("\n")
                # Remove first line (```json or ```) and last line (```)
                lines = [l for l in lines if not l.strip().startswith("```")]
                raw = "\n".join(lines)
            events_data = json.loads(raw)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(
                "summary_parse_error",
                extra={"error_type": type(e).__name__, "error_message": str(e)[:200]},
            )
            return {
                "events_created": 0,
                "reminders_created": 0,
                "summary_text": "Could not parse summary from the conversation.",
                "cards": [],
            }

        if not isinstance(events_data, list):
            logger.warning("summary_invalid_format", extra={"type": type(events_data).__name__})
            return {
                "events_created": 0,
                "reminders_created": 0,
                "summary_text": "Summary returned unexpected format.",
                "cards": [],
            }

        # Build pet name lookup (case-insensitive)
        pet_lookup: dict[str, Pet] = {p.name.lower(): p for p in pets}

        events_created = 0
        reminders_created = 0
        cards = []
        summary_parts = []

        for item in events_data:
            if not isinstance(item, dict):
                continue

            pet_name = item.get("pet_name", "")
            pet = pet_lookup.get(pet_name.lower())
            if pet is None:
                logger.debug("summary_skip_unmatched_pet", extra={"pet_name": pet_name})
                continue

            # Parse event date
            try:
                event_date = date.fromisoformat(item.get("event_date", today_str))
            except (ValueError, TypeError):
                event_date = date.today()

            title = item.get("title", "").strip()
            if not title:
                continue

            category_str = item.get("category", "daily")
            try:
                category = EventCategory(category_str)
            except ValueError:
                category = EventCategory.daily

            raw_text = item.get("raw_text", "")

            # 5. Check for duplicates
            dup_result = await db.execute(
                select(CalendarEvent).where(
                    CalendarEvent.pet_id == pet.id,
                    CalendarEvent.event_date == event_date,
                    CalendarEvent.category == category,
                    CalendarEvent.title == title,
                )
            )
            if dup_result.scalars().first() is not None:
                logger.debug("summary_skip_duplicate", extra={"title": title, "pet": pet.name})
                continue

            # Create CalendarEvent
            event = CalendarEvent(
                user_id=user_id,
                pet_id=pet.id,
                event_date=event_date,
                title=title,
                type=EventType.log,
                category=category,
                raw_text=raw_text,
                source=EventSource.chat,
                edited=False,
            )
            db.add(event)
            events_created += 1
            summary_parts.append(f"{pet.name}: {title} ({category.value})")

            cards.append({
                "type": "record",
                "pet_name": pet.name,
                "date": event_date.isoformat(),
                "category": category.value,
                "title": title,
            })

            # 6. Create Reminder for abnormal/medical
            if category.value in REMINDER_CATEGORIES:
                trigger_at = datetime.combine(
                    event_date + timedelta(days=3),
                    datetime.min.time(),
                )
                reminder = Reminder(
                    user_id=user_id,
                    pet_id=pet.id,
                    type="checkup",
                    title=f"Follow up: {title}",
                    body="Based on today's chat summary",
                    trigger_at=trigger_at,
                    sent=False,
                )
                db.add(reminder)
                reminders_created += 1

        await db.flush()

        summary_text = (
            "Recorded the following events:\n" + "\n".join(f"- {s}" for s in summary_parts)
            if summary_parts
            else "No health events found to record."
        )

        return {
            "events_created": events_created,
            "reminders_created": reminders_created,
            "summary_text": summary_text,
            "cards": cards,
        }
