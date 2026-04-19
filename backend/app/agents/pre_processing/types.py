"""Shared types for the pre-processing package."""

from dataclasses import dataclass


CONFIRM_THRESHOLD = 0.5  # Minimum confidence below which we don't even hint


@dataclass
class SuggestedAction:
    """A single tool-call suggestion produced by a domain detector.

    `tool_name` + `arguments` are ready-to-run (orchestrator passes them
    through validate_tool_args first). `confidence` is compared against
    NUDGE_CONFIDENCE (0.8) to decide whether to nudge the LLM.
    """
    tool_name: str
    arguments: dict
    confidence: float  # 0.0 - 1.0
    confirm_description: str = ""  # Human-readable text for confirm card
