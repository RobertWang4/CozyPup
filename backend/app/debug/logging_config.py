"""JSON structured logging configuration."""

import json
import logging
import traceback
from datetime import datetime, timezone

from .correlation import get_correlation_context


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        context = get_correlation_context()

        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "correlation_id": context["correlation_id"],
            "user_id": context["user_id"],
            "pet_id": context["pet_id"],
            "message": record.getMessage(),
            "extra": {},
        }

        # Include any extra fields attached to the record
        standard_attrs = logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
        for key, value in record.__dict__.items():
            if key not in standard_attrs and key not in ("message", "msg"):
                entry["extra"][key] = value

        if record.exc_info and record.exc_info[0] is not None:
            entry["error"] = {
                "type": record.exc_info[0].__name__,
                "traceback": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(entry, default=str)


def setup_logging(level: str = "DEBUG") -> None:
    """Configure root logger with JSONFormatter on a StreamHandler."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.DEBUG))

    # Remove existing handlers to avoid duplicates
    root.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    # Set specific module log levels
    logging.getLogger("app.agents").setLevel(logging.DEBUG)
    logging.getLogger("app.db").setLevel(logging.DEBUG)
    logging.getLogger("app.middleware").setLevel(logging.INFO)
