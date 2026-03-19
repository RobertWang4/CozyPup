"""LLM-based intent router — classifies user messages into action intents."""

import json
import logging

import litellm

from app.agents.prompts import ROUTER_PROMPT
from app.config import settings

logger = logging.getLogger(__name__)

VALID_INTENTS = {"chat", "summarize", "map", "email"}


async def route_intent(
    message: str,
    context_messages: list[dict],
) -> str:
    """Classify user intent using the cheap LLM model.

    Args:
        message: The current user message.
        context_messages: Last N conversation messages (role/content dicts).

    Returns:
        One of: "chat", "summarize", "map", "email". Defaults to "chat" on error.
    """
    # Build messages for the router LLM — system prompt + last 10 context + current
    last_10 = context_messages[-10:] if len(context_messages) > 10 else context_messages
    llm_messages = [
        {"role": "system", "content": ROUTER_PROMPT},
        *last_10,
        {"role": "user", "content": message},
    ]

    try:
        response = await litellm.acompletion(
            model=settings.cheap_model,
            messages=llm_messages,
            temperature=0,
            max_tokens=50,
        )
        raw = response.choices[0].message.content.strip()
        parsed = json.loads(raw)
        intent = parsed.get("intent", "chat")

        if intent not in VALID_INTENTS:
            logger.warning("router_invalid_intent", extra={"raw": raw, "intent": intent})
            return "chat"

        logger.info("router_result", extra={"intent": intent, "message_preview": message[:100]})
        return intent

    except Exception as e:
        logger.warning(
            "router_fallback",
            extra={"error_type": type(e).__name__, "error_message": str(e)[:200]},
        )
        return "chat"
