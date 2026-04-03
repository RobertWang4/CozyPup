"""Deterministic post-processor — last-resort fallback that executes
pre-analyzed actions when both the LLM and the nudge mechanism failed
to call the expected tools.

Only high-confidence (≥0.8) suggested actions are executed.
Zero additional LLM calls needed.
"""

import json
import logging
from typing import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.constants import maybe_await
from app.agents.pre_processing import SuggestedAction
from app.agents.tools import execute_tool
from app.agents.validation import validate_tool_args

logger = logging.getLogger(__name__)


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
                    await maybe_await(on_card, result["card"])

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
