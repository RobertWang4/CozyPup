"""Local admin CLI config stored at ~/.cozypup/admin.json (mode 0600)."""
from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class AdminConfig:
    token: str | None = None
    token_expires_at: int | None = None   # epoch seconds
    default_env: Literal["prod", "dev"] = "prod"
    email: str | None = None
    recent_user_ids: list[str] = field(default_factory=list)

    @staticmethod
    def default_path() -> Path:
        return Path(os.path.expanduser("~")) / ".cozypup" / "admin.json"

    @classmethod
    def load(cls) -> "AdminConfig":
        path = cls.default_path()
        if not path.exists():
            return cls()
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(
                f"{path} must be mode 0600 (currently {oct(mode)}); run `chmod 600 {path}`"
            )
        try:
            raw = json.loads(path.read_text())
        except json.JSONDecodeError:
            return cls()
        return cls(**{k: raw.get(k) for k in cls.__dataclass_fields__ if k in raw})

    def save(self) -> None:
        path = self.default_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2))
        os.chmod(tmp, 0o600)
        tmp.replace(path)
        os.chmod(path, 0o600)

    def clear_token(self) -> None:
        self.token = None
        self.token_expires_at = None
        self.email = None
