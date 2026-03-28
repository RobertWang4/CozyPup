"""Daily task intent detection for pre-processing."""

import re
from datetime import date, timedelta

from app.agents.locale import t
from .types import SuggestedAction
from .date_utils import resolve_date
from .pet_utils import resolve_pets


_DAILY_TASK_PATTERNS = [
    re.compile(
        r"(?:设置|设定|添加|加个|弄个|帮我).*(?:每天|每日|日常|常规)"
        r"|每天.*(?:要|得|需要|记得)"
        r"|(?:接下来|未来|之后|今后).*每天"
        r"|set up.*daily|add.*daily.*task|every day.*(?:need|should|must)",
        re.I,
    ),
]

_SPECIAL_TASK_PATTERN = re.compile(
    r"接下来|未来|之后|今后.*(?:\d+[天日周])"
    r"|for the next|next \d+ days|next week",
    re.I,
)

_TARGET_PATTERN = re.compile(
    r"(\d+)\s*次|([一二三四五六七八九十])\s*次"
    r"|(\d+)\s*times",
    re.I,
)

_CN_NUMS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

_DURATION_PATTERN = re.compile(
    r"(\d+)\s*[天日]|([一二三四五六七八九十])\s*[天日]"
    r"|一\s*周|(\d+)\s*周"
    r"|(\d+)\s*days|(\d+)\s*weeks?",
    re.I,
)


def _extract_target(message: str) -> int:
    m = _TARGET_PATTERN.search(message)
    if not m:
        return 1
    if m.group(1):
        return int(m.group(1))
    if m.group(2):
        return _CN_NUMS.get(m.group(2), 1)
    if m.group(3):
        return int(m.group(3))
    return 1


def _extract_duration_days(message: str) -> int | None:
    if "一周" in message or "一个星期" in message:
        return 7
    m = _DURATION_PATTERN.search(message)
    if not m:
        return None
    if m.group(1):
        return int(m.group(1))
    if m.group(2):
        return _CN_NUMS.get(m.group(2), 1)
    if m.group(3):
        return int(m.group(3)) * 7
    if m.group(4):
        return int(m.group(4))
    if m.group(5):
        return int(m.group(5)) * 7
    return None


def detect(
    message: str,
    pets: list,
    today: date,
    lang: str,
    is_question: bool,
) -> list[SuggestedAction]:
    if is_question:
        return []

    matched = False
    for pattern in _DAILY_TASK_PATTERNS:
        if pattern.search(message):
            matched = True
            break
    if not matched:
        return []

    actions: list[SuggestedAction] = []
    target = _extract_target(message)
    is_special = bool(_SPECIAL_TASK_PATTERN.search(message))

    args: dict = {
        "title": message[:100],
        "type": "special" if is_special else "routine",
        "daily_target": target,
    }

    if pets:
        resolved = resolve_pets(message, pets)
        if len(resolved) == 1:
            args["pet_id"] = resolved[0][0]

    if is_special:
        duration = _extract_duration_days(message)
        if duration:
            args["start_date"] = today.isoformat()
            args["end_date"] = (today + timedelta(days=duration - 1)).isoformat()
            desc = t("confirm_create_special_task", lang).format(
                title=message[:50], start=args["start_date"],
                end=args["end_date"], target=target,
            )
        else:
            desc = t("confirm_create_daily_task", lang).format(title=message[:50], target=target)
    else:
        desc = t("confirm_create_daily_task", lang).format(title=message[:50], target=target)

    actions.append(SuggestedAction(
        tool_name="create_daily_task",
        arguments=args,
        confidence=0.85,
        confirm_description=desc,
    ))
    return actions
