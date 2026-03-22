"""Rule-based intent detection — decide whether RAG retrieval is needed."""

import re

# Question indicators — if ANY of these appear, always retrieve
_QUESTION_PATTERNS = re.compile(
    r"[?？]"
    r"|怎么|为什么|多久|多少|上次|历史|记录|最近|之前|以前|几次|哪天"
    r"|how|when|why|what|which|last time|history|recent|before",
    re.IGNORECASE,
)

# Pure recording patterns — skip retrieval only if NONE of the question patterns match
_RECORDING_PATTERNS = re.compile(
    r"吃了|喂了|喂食|打了|打针|遛了|遛狗|拉了|吐了"
    r"|要去看|去医院|去打|去做|散步了|洗澡了"
    r"|^fed |^gave |^walked |^took .* to vet",
    re.IGNORECASE,
)


def needs_retrieval(message: str) -> bool:
    """Determine if a message needs RAG retrieval.

    Returns False only for clear recording-only messages.
    Default: True (when unsure, always retrieve).
    """
    # If any question indicator is present, always retrieve
    if _QUESTION_PATTERNS.search(message):
        return True

    # If it looks like a pure recording action, skip retrieval
    if _RECORDING_PATTERNS.search(message):
        return False

    # Default: retrieve
    return True
