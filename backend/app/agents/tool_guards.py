"""Server-side guardrails and argument backfills for tool dispatch."""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any

from app.agents.tool_context import ToolDispatchContext
from app.agents.tool_invocation import ToolInvocation

logger = logging.getLogger(__name__)


def _pet_id(pet: Any) -> str:
    return str(pet.id if hasattr(pet, "id") else pet.get("id", ""))


def _pet_name(pet: Any) -> str:
    return (pet.name if hasattr(pet, "name") else pet.get("name", "")) or ""


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    user_msgs = [
        m.get("content", "")
        for m in messages
        if m.get("role") == "user" and isinstance(m.get("content"), str)
    ]
    return user_msgs[-1] if user_msgs else ""


def apply_tool_guards(
    invocation: ToolInvocation,
    context: ToolDispatchContext,
    *,
    today: date | None = None,
) -> dict[str, Any] | None:
    """Apply deterministic guardrails before confirm/validation/execution.

    Returns a blocking tool result when a guard rejects the call. Otherwise it
    returns None and may mutate invocation.arguments with safe backfilled values.
    """
    name = invocation.name
    args = invocation.arguments
    pets = context.pets
    last_user = _last_user_text(context.messages)

    if name == "create_calendar_event" and args.get("pet_id") and pets:
        mentioned_pet_ids = {
            _pet_id(p)
            for p in pets
            if _pet_name(p) and _pet_name(p).lower() in last_user.lower()
        }
        if mentioned_pet_ids and args["pet_id"] not in mentioned_pet_ids:
            blocked_name = ""
            for pet in pets:
                if _pet_id(pet) == args["pet_id"]:
                    blocked_name = _pet_name(pet)
                    break
            logger.info("pet_mismatch_blocked", extra={
                "blocked_pet": blocked_name,
                "mentioned": list(mentioned_pet_ids),
                "user_text": last_user[:60],
            })
            return {
                "success": False,
                "error": f"用户只提到了特定的宠物，没有提到{blocked_name}。请只为用户提到的宠物创建事件。",
            }

    if name == "create_pet" and args.get("name") and pets:
        new_name = str(args["name"]).strip().lower()
        for pet in pets:
            existing_name = _pet_name(pet)
            existing_id = _pet_id(pet)
            if existing_name.strip().lower() == new_name:
                logger.info("duplicate_pet_blocked", extra={
                    "pet_name": new_name,
                    "existing_id": existing_id,
                })
                return {
                    "success": False,
                    "error": (
                        f"宠物「{existing_name}」已经存在 (id={existing_id})。"
                        f"不要重复创建 — 如需补充信息，请改用 update_pet_profile 并传 pet_id。"
                    ),
                }

    if name == "create_calendar_event" and args.get("cost") is None:
        cost_match = re.search(
            r"花了?\s*(\d+(?:\.\d+)?)\s*[块元刀]?|(\d+(?:\.\d+)?)\s*[块元刀]",
            last_user,
        )
        if cost_match:
            amount = float(cost_match.group(1) or cost_match.group(2))
            args["cost"] = amount
            logger.info("cost_auto_fixed", extra={
                "extracted": amount,
                "user_text": last_user[:60],
            })

    if name == "create_daily_task" and not args.get("end_date"):
        current_date = today or date.today()
        extracted_end = None

        month_day = re.search(r"到(\d{1,2})月(\d{1,2})[号日]", last_user)
        if month_day:
            month, day = int(month_day.group(1)), int(month_day.group(2))
            year = current_date.year if month >= current_date.month else current_date.year + 1
            try:
                extracted_end = date(year, month, day)
            except ValueError:
                pass

        if not extracted_end:
            next_weekday = re.search(r"到?下周([一二三四五六日天])", last_user)
            if next_weekday:
                weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
                target_wd = weekday_map.get(next_weekday.group(1), 6)
                days_ahead = (target_wd - current_date.weekday()) % 7 + 7
                extracted_end = current_date + timedelta(days=days_ahead)

        if not extracted_end:
            next_days = re.search(r"接下来(\d+)天", last_user)
            if next_days:
                extracted_end = current_date + timedelta(days=int(next_days.group(1)))

        if not extracted_end and re.search(r"[这本]周", last_user):
            days_to_sunday = 6 - current_date.weekday()
            extracted_end = current_date + timedelta(days=max(days_to_sunday, 1))

        if extracted_end:
            args["end_date"] = extracted_end.isoformat()
            logger.info("end_date_auto_fixed", extra={
                "extracted": extracted_end.isoformat(),
                "user_text": last_user[:60],
            })

    return None
