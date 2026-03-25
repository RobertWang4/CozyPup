"""Emergency detection — keyword-based check for urgent pet health situations."""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmergencyCheckResult:
    detected: bool
    keywords: list[str]

EMERGENCY_KEYWORDS: list[str] = [
    # English
    "seizure",
    "poison",
    "choking",
    "bleeding",
    "difficulty breathing",
    "collapse",
    "not breathing",
    "unconscious",
    "hit by car",
    "swallowed",
    "ingested",
    "toxic",
    "convulsion",
    "hemorrhage",
    "paralysis",
    "bloat",
    "heatstroke",
    "frostbite",
    "drowning",
    "electric shock",
    "snake bite",
    "bee sting",
    "allergic reaction",
    # Chinese
    "抽搐",
    "中毒",
    "窒息",
    "出血",
    "大出血",
    "呼吸困难",
    "不呼吸",
    "昏迷",
    "晕倒",
    "被车撞",
    "误食",
    "吞了",
    "有毒",
    "痉挛",
    "瘫痪",
    "腹胀",
    "胃扭转",
    "中暑",
    "冻伤",
    "溺水",
    "触电",
    "蛇咬",
    "蜜蜂蛰",
    "过敏性休克",
    "翻白眼",
    "口吐白沫",
    "站不起来",
    "急救",
    "快死了",
    "不动了",
    "没有意识",
]

# Build a single compiled regex for efficient matching.
# Word boundaries ensure partial matches (e.g. "bleeding" in "disbelieving") still
# match since the keywords are medically significant on their own.
_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in EMERGENCY_KEYWORDS),
    re.IGNORECASE,
)


def detect_emergency(message: str) -> EmergencyCheckResult:
    """Check for emergency keywords. Returns detected status and matched keywords."""
    matches = _PATTERN.findall(message)
    # deduplicate while preserving order
    unique = list(dict.fromkeys(matches))
    return EmergencyCheckResult(detected=bool(unique), keywords=unique)


def build_emergency_hint(keywords: list[str]) -> str:
    """Build a prompt hint for the LLM when emergency keywords are detected."""
    kw_str = ", ".join(keywords)
    return (
        f"\u26a0\ufe0f 检测到可能的紧急关键词: [{kw_str}].\n"
        "请仔细判断这是否为真正的宠物紧急情况。\n"
        "如果是真正的紧急情况（宠物生命受到威胁），请调用 trigger_emergency 工具。\n"
        "如果用户只是在询问过去的事件、一般性讨论或轻微不适，不要触发紧急操作。"
    )
