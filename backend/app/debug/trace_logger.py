"""Always-on request trace logger.

Writes structured JSON logs to the `cozypup.trace` logger at each
pipeline step.  correlation_id and user_id are pulled from ContextVars
(set by CorrelationMiddleware).  All output goes to stdout and is
automatically collected by Cloud Logging on Cloud Run.
"""

import json
import logging
from typing import Any

from .correlation import get_correlation_id, get_user_id

_logger = logging.getLogger("cozypup.trace")

# Cloud Logging caps a single entry at 256 KB; leave headroom for the envelope.
TRACE_MAX_CHARS = 200_000


def messages_for_trace(messages: list[dict], max_chars: int = TRACE_MAX_CHARS) -> list[dict] | dict:
    """Return a loggable copy of the full LLM `messages` array.

    Inline images (multimodal content parts) are replaced with a placeholder
    so base64 blobs never reach the logs. If the result would still exceed
    `max_chars`, a small truncation marker is returned instead.
    """
    out: list[dict] = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            content = [
                {"type": "image_url", "image_url": "<omitted>"}
                if isinstance(part, dict) and part.get("type") == "image_url"
                else part
                for part in content
            ]
            m = {**m, "content": content}
        out.append(m)
    size = len(json.dumps(out, ensure_ascii=False, default=str))
    if size > max_chars:
        return {"_truncated": True, "_size": size, "message_count": len(messages)}
    return out


def trace_log(
    log_type: str,
    *,
    round: int | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Emit a single trace log entry.

    Args:
        log_type: One of chat_request, llm_request, llm_response,
                  tool_call, tool_result, chat_response.
        round: Orchestrator round number (0-indexed).
        data: Arbitrary payload for this step.
    """
    entry: dict[str, Any] = {
        "log_type": log_type,
        "correlation_id": get_correlation_id(),
        "user_id": get_user_id(),
    }
    if round is not None:
        entry["round"] = round
    if data:
        entry["data"] = data

    _logger.info(json.dumps(entry, ensure_ascii=False, default=str))
