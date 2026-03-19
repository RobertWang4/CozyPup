"""Emergency detection — keyword-based check for urgent pet health situations."""

import logging
import re

logger = logging.getLogger(__name__)

EMERGENCY_KEYWORDS: list[str] = [
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
]

# Build a single compiled regex for efficient matching.
# Word boundaries ensure partial matches (e.g. "bleeding" in "disbelieving") still
# match since the keywords are medically significant on their own.
_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in EMERGENCY_KEYWORDS),
    re.IGNORECASE,
)


def detect_emergency(message: str) -> bool:
    """Return True if the message contains any emergency keyword."""
    return bool(_PATTERN.search(message))
