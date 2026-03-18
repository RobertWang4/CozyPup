"""Error snapshot creation and persistence."""

import json
import traceback as tb
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOTS_DIR = Path("logs/error_snapshots")


@dataclass
class ErrorSnapshot:
    correlation_id: str
    timestamp: str
    category: str
    module: str
    error_type: str
    error_message: str
    traceback: str
    fingerprint: str
    request_data: dict
    correlation_context: dict
    agent_state: dict | None = None
    db_context: dict | None = None


def capture_error(
    exc: Exception,
    request_data: dict = None,
    agent_state: dict = None,
    db_context: dict = None,
) -> ErrorSnapshot:
    """Create an ErrorSnapshot from an exception."""
    from .correlation import get_correlation_context, get_correlation_id
    from .fingerprint import compute_fingerprint
    from .error_types import ErrorCategory, PetPalError

    if isinstance(exc, PetPalError):
        category = exc.category.value
        module = exc.module
    else:
        category = ErrorCategory.UNKNOWN.value
        module = type(exc).__module__ or "unknown"

    error_type = type(exc).__name__
    error_message = str(exc)
    fingerprint = compute_fingerprint(error_type, module, error_message)

    return ErrorSnapshot(
        correlation_id=get_correlation_id(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        category=category,
        module=module,
        error_type=error_type,
        error_message=error_message,
        traceback=tb.format_exc(),
        fingerprint=fingerprint,
        request_data=request_data or {},
        correlation_context=get_correlation_context(),
        agent_state=agent_state,
        db_context=db_context,
    )


def save_snapshot(snapshot: ErrorSnapshot) -> Path:
    """Persist an ErrorSnapshot as JSON. Returns the file path."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOTS_DIR / f"{snapshot.correlation_id}.json"
    path.write_text(json.dumps(asdict(snapshot), indent=2))
    return path


def load_snapshot(correlation_id: str) -> ErrorSnapshot:
    """Load an ErrorSnapshot from disk by correlation ID."""
    path = SNAPSHOTS_DIR / f"{correlation_id}.json"
    data = json.loads(path.read_text())
    return ErrorSnapshot(**data)
