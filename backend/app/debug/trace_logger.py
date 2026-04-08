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
