"""Stable trace artifact schema for agent harness runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .client import ChatResult, get_tools_called


@dataclass(frozen=True)
class TraceArtifact:
    schema_version: int
    scenario_id: str | None
    user_email: str | None
    input_messages: list[str]
    output_text: str
    tools_called: list[str]
    cards: list[dict[str, Any]]
    elapsed_ms: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    raw_trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceArtifact":
        return cls(
            schema_version=int(data["schema_version"]),
            scenario_id=data.get("scenario_id"),
            user_email=data.get("user_email"),
            input_messages=list(data.get("input_messages", [])),
            output_text=str(data.get("output_text", "")),
            tools_called=list(data.get("tools_called", [])),
            cards=list(data.get("cards", [])),
            elapsed_ms=int(data.get("elapsed_ms", 0)),
            total_prompt_tokens=int(data.get("total_prompt_tokens", 0)),
            total_completion_tokens=int(data.get("total_completion_tokens", 0)),
            total_tokens=int(data.get("total_tokens", 0)),
            raw_trace=dict(data.get("raw_trace", {})),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def normalize_trace_artifact(
    *,
    scenario_id: str | None,
    user_email: str | None,
    input_messages: list[str],
    result: ChatResult,
) -> TraceArtifact:
    trace = result.trace or {}
    prompt = int(trace.get("total_prompt_tokens") or 0)
    completion = int(trace.get("total_completion_tokens") or 0)
    total = int(trace.get("total_tokens") or prompt + completion)

    return TraceArtifact(
        schema_version=1,
        scenario_id=scenario_id,
        user_email=user_email,
        input_messages=input_messages,
        output_text=result.text,
        tools_called=get_tools_called(result),
        cards=result.cards,
        elapsed_ms=result.elapsed_ms,
        total_prompt_tokens=prompt,
        total_completion_tokens=completion,
        total_tokens=total,
        raw_trace=trace,
    )
