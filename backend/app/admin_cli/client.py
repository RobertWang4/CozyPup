"""HTTPS client for the admin CLI. Thin wrapper over httpx."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from .config import AdminConfig


class AdminClientError(RuntimeError):
    pass


@dataclass
class Envelope:
    data: Any
    audit_id: str | None
    env: str | None


class AdminClient:
    def __init__(self, config: AdminConfig, env: str | None = None, timeout: float = 30.0):
        self.config = config
        self.env = env or config.default_env
        default = (
            "https://backend-601329501885.northamerica-northeast1.run.app"
            if self.env == "prod"
            else "http://localhost:8000"
        )
        self.base_url = os.environ.get(f"COZYPUP_ADMIN_BASE_URL_{self.env.upper()}", default)
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json", "User-Agent": "cozypup-admin/0.1"}
        if self.config.token:
            h["Authorization"] = f"Bearer {self.config.token}"
        return h

    def _raise_for_status(self, r: httpx.Response) -> None:
        if r.status_code // 100 != 2:
            try:
                detail = r.json().get("detail")
            except Exception:
                detail = r.text[:200]
            raise AdminClientError(f"{r.status_code} {r.request.url}: {detail}")

    def _decode(self, r: httpx.Response) -> Envelope:
        try:
            body = r.json()
        except Exception as e:
            raise AdminClientError(f"non-JSON response: {e}")
        if not isinstance(body, dict) or "data" not in body:
            raise AdminClientError(f"envelope missing 'data': {body}")
        return Envelope(data=body.get("data"), audit_id=body.get("audit_id"), env=body.get("env"))

    def _url(self, path: str) -> str:
        if path.startswith("/api"):
            return f"{self.base_url}{path}"
        return f"{self.base_url}/api/v1{path}"

    def get(self, path: str, params: dict | None = None) -> Envelope:
        r = httpx.get(self._url(path), params=params, headers=self._headers(), timeout=self._timeout)
        self._raise_for_status(r)
        return self._decode(r)

    def post(self, path: str, body: dict) -> Envelope:
        r = httpx.post(self._url(path), json=body, headers=self._headers(), timeout=self._timeout)
        self._raise_for_status(r)
        return self._decode(r)
