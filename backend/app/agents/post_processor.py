"""Deterministic post-processor — executes pre-analyzed actions when the LLM
fails to call tools but claims it performed an action.

This replaces the LLM retry mechanism (_retry_with_forced_tool) with instant
deterministic execution. Zero additional LLM calls needed.
"""

import json
import logging
import re
from typing import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pre_processor import SuggestedAction
from app.agents.tools import execute_tool
from app.agents.validation import validate_tool_args

logger = logging.getLogger(__name__)

# Patterns indicating the LLM claimed to perform an action
_CLAIMED_ACTION = re.compile(
    r"已记录|已更新|已保存|已添加|已设置|记住了|帮你记|帮你添加|帮你设"
    r"|I'?ve recorded|I'?ve updated|I'?ve saved|I'?ve added|I'?ve set"
    r"|I recorded|I updated|I saved|I added|I created"
    r"|recorded it|saved it|added it|updated it|created it",
    re.IGNORECASE,
)


def response_claims_action(response_text: str) -> bool:
    """Check if the LLM's response text claims it performed an action."""
    return bool(_CLAIMED_ACTION.search(response_text))


async def execute_suggested_actions(
    suggested_actions: list[SuggestedAction],
    db: AsyncSession,
    user_id: UUID,
    on_card: Callable | None = None,
    location: dict | None = None,
) -> list[dict]:
    """Execute pre-analyzed actions deterministically.

    Called when the LLM claimed an action but didn't actually call any tools.
    Uses the pre-processor's suggested actions to execute without any LLM calls.

    Returns:
        List of card dicts from successful tool executions.
    """
    cards: list[dict] = []

    for action in suggested_actions:
        if action.confidence < 0.8:
            continue  # Only execute high-confidence actions

        # Validate arguments
        errors = validate_tool_args(action.tool_name, action.arguments)
        if errors:
            logger.warning(
                "post_processor_validation_failed",
                extra={"tool": action.tool_name, "errors": errors},
            )
            continue

        try:
            kwargs = {}
            if action.tool_name == "search_places":
                kwargs["location"] = location

            result = await execute_tool(
                action.tool_name, action.arguments, db, user_id, **kwargs
            )
            await db.commit()

            if "card" in result:
                cards.append(result["card"])
                if on_card:
                    coro = on_card(result["card"])
                    if hasattr(coro, "__await__"):
                        await coro

            logger.info(
                "post_processor_executed",
                extra={"tool": action.tool_name, "success": result.get("success", True)},
            )
        except Exception as exc:
            logger.error(
                "post_processor_error",
                extra={"tool": action.tool_name, "error": str(exc)[:200]},
            )

    return cards
