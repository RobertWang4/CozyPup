"""Shared types for the pre-processing package."""

from dataclasses import dataclass


CONFIRM_THRESHOLD = 0.5  # Minimum confidence for confirm card


@dataclass
class SuggestedAction:
    tool_name: str
    arguments: dict
    confidence: float  # 0.0 - 1.0
    confirm_description: str = ""  # Human-readable description for confirm card
