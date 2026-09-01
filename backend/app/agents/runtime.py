"""Shared agent runtime contracts.

These types are intentionally small. They give the HTTP route, CLI harness,
future eval runner, and later AgentEngine a common vocabulary without changing
the current orchestrator loop yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RunStatus(StrEnum):
    SUCCESS = "success"
    MAX_ROUNDS = "max_rounds"
    TOOL_ERROR = "tool_error"
    PERMISSION_DENIED = "permission_denied"
    MODEL_ERROR = "model_error"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True)
class AgentEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> dict[str, Any]:
        return {"event": self.type, "data": self.data}


@dataclass
class AgentRunResult:
    status: RunStatus
    response_text: str = ""
    cards: list[dict[str, Any]] = field(default_factory=list)
    confirm_cards: list[dict[str, Any]] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    tools_executed: list[str] = field(default_factory=list)
    rounds: int = 0
    elapsed_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model_used: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == RunStatus.SUCCESS

    @classmethod
    def success(cls, **kwargs):
        return cls(status=RunStatus.SUCCESS, **kwargs)
