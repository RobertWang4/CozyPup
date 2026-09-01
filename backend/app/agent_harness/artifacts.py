"""JSON artifact I/O helpers for the agent harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(path: str | Path, data: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return target


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())
