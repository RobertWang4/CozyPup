"""Per-request trace collector — records every pipeline step for debugging.

Activated by X-Debug: true header. Zero overhead when inactive.
Trace data is emitted as `event: __debug__` SSE events at the end of the stream.
"""

import time
import json
from dataclasses import dataclass, field


@dataclass
class TraceCollector:
    """Collects pipeline trace data for a single request."""

    active: bool = False
    steps: list[dict] = field(default_factory=list)
    llm_rounds: list[dict] = field(default_factory=list)
    start_time: float = field(default_factory=time.monotonic)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0

    def record(self, step: str, data: dict | str | None = None):
        """Record a pipeline step with timing."""
        if not self.active:
            return
        entry = {
            "step": step,
            "elapsed_ms": int((time.monotonic() - self.start_time) * 1000),
        }
        if data is not None:
            entry["data"] = data if isinstance(data, (dict, list)) else str(data)
        self.steps.append(entry)

    def record_llm_response(self, round_num: int, raw_response: dict):
        """Record a full non-streaming LLM response JSON."""
        if not self.active:
            return
        # Extract usage
        usage = raw_response.get("usage", {})
        if isinstance(usage, dict):
            self.total_prompt_tokens += usage.get("prompt_tokens", 0)
            self.total_completion_tokens += usage.get("completion_tokens", 0)

        self.llm_rounds.append({
            "round": round_num,
            "elapsed_ms": int((time.monotonic() - self.start_time) * 1000),
            "response": raw_response,
        })

    def to_dict(self) -> dict:
        """Export trace as a serializable dict."""
        return {
            "total_elapsed_ms": int((time.monotonic() - self.start_time) * 1000),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "steps": self.steps,
            "llm_rounds": self.llm_rounds,
        }


# Sentinel for inactive trace — all methods are no-ops
INACTIVE_TRACE = TraceCollector(active=False)
