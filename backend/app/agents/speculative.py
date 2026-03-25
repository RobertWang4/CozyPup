"""
Speculative Execution: Pre-execute high-confidence actions without committing.

Like CPU branch prediction -- start executing before LLM confirms.
If LLM confirms the same action -> commit (zero extra latency).
If LLM does something different -> rollback.

Only for non-destructive operations with confidence >= 0.8.
"""

import json
import logging
from dataclasses import dataclass, field

from app.agents.tools import execute_tool
from app.agents.validation import validate_tool_args

logger = logging.getLogger(__name__)

DESTRUCTIVE_TOOLS = {"delete_pet", "delete_calendar_event", "delete_reminder"}


@dataclass
class SpeculativeResult:
    """Result of a speculative execution (not committed yet)."""

    tool_name: str
    arguments: dict
    result: dict | None = None
    card: dict | None = None
    error: str | None = None
    executed: bool = False


async def speculative_execute(
    actions: list,
    db,
    user_id,
    **kwargs,
) -> list[SpeculativeResult]:
    """
    Pre-execute high-confidence non-destructive actions WITHOUT committing.

    The DB transaction is left open -- caller must commit or rollback.

    Args:
        actions: List of SuggestedAction from pre_processor
        db: AsyncSession (DO NOT commit here)
        user_id: User ID for ownership checks

    Returns:
        List of SpeculativeResult
    """
    results = []

    for action in actions:
        # Only high confidence, non-destructive
        if action.confidence < 0.8:
            continue
        if action.tool_name in DESTRUCTIVE_TOOLS:
            continue

        # Validate arguments first
        errors = validate_tool_args(action.tool_name, action.arguments)
        if errors:
            results.append(SpeculativeResult(
                tool_name=action.tool_name,
                arguments=action.arguments,
                error=f"Validation: {'; '.join(errors)}",
            ))
            continue

        try:
            # Execute but DO NOT commit
            tool_result = await execute_tool(
                action.tool_name, action.arguments, db, user_id, **kwargs
            )
            # Note: we intentionally do NOT call db.commit() here

            results.append(SpeculativeResult(
                tool_name=action.tool_name,
                arguments=action.arguments,
                result=tool_result,
                card=tool_result.get("card"),
                executed=True,
            ))

            logger.info("speculative_executed", extra={
                "tool": action.tool_name,
                "confidence": action.confidence,
            })

        except Exception as exc:
            results.append(SpeculativeResult(
                tool_name=action.tool_name,
                arguments=action.arguments,
                error=str(exc),
            ))

    return results


def match_speculative(
    speculative_results: list[SpeculativeResult],
    actual_tool_name: str,
    actual_arguments: dict,
) -> SpeculativeResult | None:
    """
    Check if any speculative result matches what the LLM actually decided.

    Match criteria: same tool name + same key arguments.
    """
    for spec in speculative_results:
        if not spec.executed:
            continue
        if spec.tool_name != actual_tool_name:
            continue

        # Check key arguments match (allow minor differences like title wording)
        spec_args = spec.arguments
        actual_args = actual_arguments

        # Must match: pet_id, event_date, category (for calendar events)
        key_fields = [
            "pet_id", "event_date", "category",
            "pet_ids", "reminder_id", "event_id",
        ]
        match = True
        for key in key_fields:
            if key in spec_args or key in actual_args:
                if spec_args.get(key) != actual_args.get(key):
                    match = False
                    break

        if match:
            return spec

    return None


async def commit_or_rollback(
    speculative_results: list[SpeculativeResult],
    actual_tool_calls: list[dict],
    db,
) -> list[SpeculativeResult]:
    """
    Compare speculative results with what the LLM actually did.
    Commit matches, rollback mismatches.

    Returns: list of matched (committed) speculative results
    """
    matched = []
    unmatched_specs = list(speculative_results)

    for tc in actual_tool_calls:
        fn_name = tc.get("function", {}).get("name", "")
        try:
            fn_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
        except json.JSONDecodeError:
            continue

        spec = match_speculative(unmatched_specs, fn_name, fn_args)
        if spec:
            matched.append(spec)
            unmatched_specs.remove(spec)

    if matched and not unmatched_specs:
        # All speculative executions matched -- commit
        await db.commit()
        logger.info("speculative_committed", extra={
            "matched_count": len(matched),
        })
    elif unmatched_specs:
        # Some speculative executions didn't match -- rollback all
        await db.rollback()
        logger.warning("speculative_rollback", extra={
            "matched": len(matched),
            "unmatched": len(unmatched_specs),
        })
        matched = []  # All rolled back

    return matched
