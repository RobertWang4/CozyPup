"""High-precision intent detection to steer retrieval away from known traps.

The problem we're solving: pure vector similarity keeps collapsing
"dog ate chocolate" / "dog ate ibuprofen" / "cat ate lily" into the
"Swallowed Foreign Objects" article, because "dog/cat ate X" is a strong
semantic prior. The right articles (Toxic Foods / Toxic Plants / Human
Medications Toxic) lose the race.

We use rules, not a classifier — only act on patterns that are unambiguous
enough to be safe. Every rule is additive ("also search these articles");
we never EXCLUDE articles based on intent, because a mis-classification
could hide the right answer. Worst case of a mis-detect is we do a slightly
broader search than needed.

This module does not fabricate medical facts. It only decides which article
titles to surface as a secondary candidate pool in the existing knowledge base.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Keyword gazetteers — matched case-insensitively, bilingual.
# Additive only; errors are benign (at worst: extra articles considered).
# ---------------------------------------------------------------------------

_INGESTION_VERBS = re.compile(
    r"(吃了|吃下|误食|吞了|吞下|误吞|偷吃|舔了|舔食|喝了|喝下|"
    r"ate\b|ingested\b|swallowed\b|consumed\b|got into\b)",
    re.IGNORECASE,
)

_TOXIC_FOOD_TERMS = re.compile(
    r"(巧克力|葡萄|葡萄干|洋葱|大蒜|韭菜|木糖醇|xylitol|chocolate|grape|raisin|"
    r"onion|garlic|chive|macadamia|avocado|咖啡|caffeine|酒|alcohol)",
    re.IGNORECASE,
)

_TOXIC_PLANT_TERMS = re.compile(
    r"(百合|lily|绿萝|pothos|水仙|daffodil|杜鹃|azalea|郁金香|tulip|"
    r"万年青|dieffenbachia|芦荟|aloe|花粉|花叶)",
    re.IGNORECASE,
)

_TOXIC_MED_TERMS = re.compile(
    r"(布洛芬|ibuprofen|对乙酰氨基酚|acetaminophen|tylenol|泰诺|阿司匹林|aspirin|"
    r"感冒药|cold medicine|止痛药|painkiller|抗抑郁|antidepressant|安眠|sleeping pill|"
    r"避孕|人用药|人药|人用)",
    re.IGNORECASE,
)

_FOREIGN_OBJECT_TERMS = re.compile(
    r"(袜子|塑料|绳子|线|玩具|骨头|石头|硬币|电池|磁铁|橡皮筋|纽扣|"
    r"sock|string|rope|toy|bone|rock|coin|battery|magnet|rubber band|button)",
    re.IGNORECASE,
)


@dataclass
class IntentHint:
    """Articles to ALSO retrieve from, alongside the default vector search.

    `boost_title_patterns` is a list of case-insensitive substrings; articles
    whose title matches any of them join the candidate pool for a second
    vector search. Results are unioned with the main search.
    """
    label: str
    boost_title_patterns: list[str] = field(default_factory=list)


# Article titles seeded from the current knowledge base. Using substrings
# rather than category filters because "Toxic Foods", "Toxic Plants", "Human
# Medications Toxic" and "Swallowed Foreign Objects" all share category
# "emergency" — only title text disambiguates them.
_TITLE_TOXIC_FOODS = "toxic foods"
_TITLE_TOXIC_PLANTS = "toxic plants"
_TITLE_HUMAN_MEDS = "human medications"
_TITLE_FOREIGN_OBJECTS = "foreign objects"
_TITLE_EMERGENCY_GENERIC = "pet emergencies"


def detect_intent(query: str) -> IntentHint | None:
    """Return an additive retrieval hint, or None if no pattern fires.

    Decision tree (ordered — first match wins; patterns are mutually exclusive
    in practice because a query mentioning both "chocolate" and "sock" is
    essentially never seen in real traffic):
      1. Ingestion verb + toxic food term
      2. Ingestion verb + toxic plant term
      3. Ingestion verb + human med term
      4. Ingestion verb + foreign-object term
      5. Otherwise → None (default vector search only)
    """
    if not query:
        return None
    if not _INGESTION_VERBS.search(query):
        return None

    if _TOXIC_FOOD_TERMS.search(query):
        return IntentHint(
            "toxin_food",
            [_TITLE_TOXIC_FOODS, _TITLE_EMERGENCY_GENERIC],
        )
    if _TOXIC_PLANT_TERMS.search(query):
        return IntentHint(
            "toxin_plant",
            [_TITLE_TOXIC_PLANTS, _TITLE_EMERGENCY_GENERIC],
        )
    if _TOXIC_MED_TERMS.search(query):
        return IntentHint(
            "toxin_medication",
            [_TITLE_HUMAN_MEDS, _TITLE_EMERGENCY_GENERIC],
        )
    if _FOREIGN_OBJECT_TERMS.search(query):
        return IntentHint(
            "foreign_object",
            [_TITLE_FOREIGN_OBJECTS, _TITLE_EMERGENCY_GENERIC],
        )
    return None
