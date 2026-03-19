"""Email agent — drafts professional vet emails from conversation context."""

import json
import logging

import litellm

from app.agents.base import BaseAgent
from app.agents.prompts import EMAIL_PROMPT
from app.config import settings

logger = logging.getLogger(__name__)


def _build_pet_context(pets: list) -> str:
    """Build a human-readable pet info string from Pet objects."""
    if not pets:
        return "No pet information available."

    lines = []
    for p in pets:
        parts = [f"- {p.name}: {p.species.value}"]
        if p.breed:
            parts.append(f", breed: {p.breed}")
        if p.weight:
            parts.append(f", weight: {p.weight}kg")
        if p.birthday:
            parts.append(f", birthday: {p.birthday.isoformat()}")
        lines.append("".join(parts))
    return "\n".join(lines)


class EmailAgent(BaseAgent):
    name = "email_agent"

    async def _run(self, message: str, context: dict, **kwargs) -> dict:
        """Draft a professional vet email based on conversation context.

        Args:
            message: The user's request (e.g. "help me write an email to the vet").
            context: Dict with keys: db, user_id, session_id, pets, context_messages.

        Returns:
            Dict with 'response' (str) and 'card' (dict with type/subject/body).
        """
        pets = context.get("pets", [])
        context_messages = context.get("context_messages", [])

        pet_context = _build_pet_context(pets)

        # Use last 10 context messages for conversation history
        recent = context_messages[-10:] if len(context_messages) > 10 else context_messages

        system_prompt = EMAIL_PROMPT.format(pet_context=pet_context)

        llm_messages = [
            {"role": "system", "content": system_prompt},
            *recent,
            {"role": "user", "content": message},
        ]

        try:
            response = await litellm.acompletion(
                model=settings.cheap_model,
                messages=llm_messages,
                temperature=0.3,
                max_tokens=1000,
            )
            raw = response.choices[0].message.content.strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                lines = raw.split("\n")
                # Remove first line (```json or ```) and last line (```)
                lines = [l for l in lines if not l.strip().startswith("```")]
                raw = "\n".join(lines).strip()

            parsed = json.loads(raw)
            subject = parsed.get("subject", "Veterinary Appointment Request")
            body = parsed.get("body", "")

            if not body:
                logger.warning("email_agent_empty_body", extra={"raw": raw[:200]})
                return {
                    "response": "I wasn't able to generate the email body. Could you provide more details about what you'd like to include?",
                    "card": None,
                }

            return {
                "response": "Here's a draft email for your vet:",
                "card": {
                    "type": "email",
                    "subject": subject,
                    "body": body,
                },
            }

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(
                "email_agent_parse_error",
                extra={"error_type": type(e).__name__, "error_message": str(e)[:200]},
            )
            return {
                "response": "I had trouble formatting the email. Could you try rephrasing your request?",
                "card": None,
            }
