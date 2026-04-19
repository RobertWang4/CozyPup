"""Pre-processing package — deterministic intent detection before the LLM call.

Runs cheap regex/keyword heuristics over the user message to produce
`SuggestedAction`s with confidence scores. These feed two mechanisms:

  1. Pre-processor hints appended to the system prompt (advisory).
  2. The orchestrator's nudge mechanism, which retries when the LLM
     skips a high-confidence suggestion for a NUDGE_TOOLS tool.

Zero LLM cost. Pure heuristics — false positives are fine because the
LLM still has final say. Only tools listed in `NUDGE_TOOLS` are ever
forced, so over-detection just means a few extra bytes in the prompt.
"""

from .types import SuggestedAction, CONFIRM_THRESHOLD
from .core import pre_process
from .date_utils import resolve_date
from .pet_utils import resolve_pets

__all__ = [
    "pre_process",
    "SuggestedAction",
    "CONFIRM_THRESHOLD",
    "resolve_date",
    "resolve_pets",
]
