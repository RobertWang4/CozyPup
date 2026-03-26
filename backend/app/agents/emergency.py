"""Emergency detection — keyword-based check for urgent pet health situations."""

import logging
import re
from dataclasses import dataclass

from app.agents.locale import t

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


def build_emergency_hint(keywords: list[str], lang: str = "zh") -> str:
    """Build a prompt hint for the LLM when emergency keywords are detected."""
    kw_str = ", ".join(keywords)
    return t("emergency_hint", lang).format(keywords=kw_str)
