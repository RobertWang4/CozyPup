"""Error fingerprinting for deduplication."""

import hashlib
import re

# UUID pattern (various formats)
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|\b[0-9a-fA-F]{32}\b"
)
# Standalone numbers (integers and floats)
_NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
# File paths
_PATH_RE = re.compile(r"(?:/[\w.\-]+)+/?")


def _normalize_message(message: str) -> str:
    """Replace variable parts of an error message with placeholders."""
    result = _UUID_RE.sub("<UUID>", message)
    result = _PATH_RE.sub("<PATH>", result)
    result = _NUM_RE.sub("<N>", result)
    return result


def compute_fingerprint(error_type: str, module: str, message: str) -> str:
    """Compute a stable fingerprint for error deduplication.

    Returns the first 16 hex chars of SHA256("{error_type}:{module}:{normalized}").
    """
    normalized = _normalize_message(message)
    raw = f"{error_type}:{module}:{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
