"""Date parsing utilities for pre-processing.

Resolves bilingual relative dates ("tomorrow", "上周三", "last Friday")
and explicit date literals. Returns None for ambiguous phrases like
"last week" (no specific day) so the calling detector can tell the LLM
to ask the user for clarification instead of guessing a date.
"""

import re
from datetime import date, timedelta


_RELATIVE_DATES = {
    "今天": 0, "今日": 0, "today": 0,
    "明天": 1, "明日": 1, "tomorrow": 1,
    "后天": 2, "大后天": 3,
    "昨天": -1, "昨日": -1, "yesterday": -1,
    "前天": -2,
}


_AMBIGUOUS_DATE = re.compile(
    r"上周(?![一二三四五六日天])|上个?月(?!\d)|前阵子|前段时间|最近|之前"
    r"|last week(?!\s*(?:mon|tue|wed|thu|fri|sat|sun))|last month",
    re.I,
)

_WEEKDAY_LAST_WEEK = {
    "上周一": 0, "上周二": 1, "上周三": 2, "上周四": 3,
    "上周五": 4, "上周六": 5, "上周日": 6, "上周天": 6,
}

# English "last Monday" → weekday index
_WEEKDAY_LAST_WEEK_EN = re.compile(
    r"last\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
    re.I,
)
_EN_WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def resolve_date(message: str, today: date) -> date | None:
    """Extract a date from the message.

    Returns None if the date is ambiguous (e.g. "上周" without specifying day).
    Returns today if no date info is found.
    """
    msg_lower = message.lower()

    # "上周一" → exact date
    for keyword, weekday in _WEEKDAY_LAST_WEEK.items():
        if keyword in msg_lower:
            days_back = (today.weekday() - weekday) % 7 + 7
            return today - timedelta(days=days_back)

    # "last Friday" → exact date
    en_match = _WEEKDAY_LAST_WEEK_EN.search(msg_lower)
    if en_match:
        weekday = _EN_WEEKDAY_MAP[en_match.group(1).lower()]
        days_back = (today.weekday() - weekday) % 7 + 7
        return today - timedelta(days=days_back)

    # Ambiguous dates → return None (caller should ask user)
    if _AMBIGUOUS_DATE.search(msg_lower):
        return None

    for keyword, delta in _RELATIVE_DATES.items():
        if keyword in msg_lower:
            return today + timedelta(days=delta)
    # Check for explicit dates like 3月23号, 3.23, 03-23
    m = re.search(r"(\d{1,2})[月.\-/](\d{1,2})[号日]?", message)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                return date(today.year, month, day)
            except ValueError:
                pass
    return today
