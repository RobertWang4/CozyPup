"""JSON structured logging configuration."""

import json
import logging
import traceback
from datetime import datetime, timezone

from .correlation import get_correlation_context


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON lines."""

    _STANDARD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())

    def format(self, record: logging.LogRecord) -> str:
        context = get_correlation_context()

        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
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
        for key, value in record.__dict__.items():
            if key not in self._STANDARD_ATTRS and key not in ("message", "msg"):
                entry["extra"][key] = value

        if record.exc_info and record.exc_info[0] is not None:
            entry["error"] = {
                "type": record.exc_info[0].__name__,
                "traceback": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(entry, default=str)


def setup_logging(level: str = "DEBUG", module_levels: dict[str, str] | None = None) -> None:
    """Configure root logger with JSONFormatter on a StreamHandler."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.DEBUG))

    # Remove existing handlers to avoid duplicates
    root.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    # Set specific module log levels
    default_module_levels = {
        "app.routers.auth": "INFO",
        "app.routers.pets": "INFO",
        "app.routers.calendar": "INFO",
        "app.routers.chat": "DEBUG",
        "app.routers.chat_history": "INFO",
        "app.routers.reminders": "INFO",
        "app.routers.devices": "INFO",
        "app.agents": "DEBUG",
        "app.auth": "INFO",
        "app.middleware": "INFO",
        "app.debug.middleware": "INFO",
        "httpx": "WARNING",
        "httpcore": "WARNING",
        "litellm": "WARNING",
    }
    effective_levels = {**default_module_levels, **(module_levels or {})}
    for module, lvl in effective_levels.items():
        logging.getLogger(module).setLevel(getattr(logging, lvl.upper(), logging.DEBUG))
