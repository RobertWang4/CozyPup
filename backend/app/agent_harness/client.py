"""Shared client utilities for agent harness runs and legacy E2E tests."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import httpx


TIMEOUT = 120.0


@dataclass
class ChatResult:
    """Structured result from one chat SSE request."""

    text: str = ""
    cards: list[dict] = field(default_factory=list)
    emergency: dict | None = None
    session_id: str | None = None
    raw_events: list[dict] = field(default_factory=list)
    elapsed_ms: int = 0
    error: str | None = None
    trace: dict | None = None

    def has_card(self, card_type: str) -> bool:
        return any(c.get("type") == card_type for c in self.cards)

    def first_card(self, card_type: str) -> dict | None:
        for c in self.cards:
            if c.get("type") == card_type:
                return c
        return None

    def all_cards(self, card_type: str) -> list[dict]:
        return [c for c in self.cards if c.get("type") == card_type]

    def card_count(self, card_type: str) -> int:
        return len(self.all_cards(card_type))

    def dump(self) -> str:
        lines = [
            f"-- LLM reply ({self.elapsed_ms}ms) --",
            self.text or "(empty)",
            "",
        ]

        if self.cards:
            lines.append(f"-- Cards ({len(self.cards)}) --")
            for i, c in enumerate(self.cards):
                lines.append(f"  [{i}] {json.dumps(c, ensure_ascii=False, indent=2)}")
        else:
            lines.append("-- Cards --\n(none)")
        lines.append("")

        if self.emergency:
            lines.append(f"-- Emergency --\n{json.dumps(self.emergency, ensure_ascii=False)}")
            lines.append("")

        if self.error:
            lines.append(f"-- Error --\n{self.error}")
            lines.append("")

        lines.append("-- Raw SSE events --")
        for evt in self.raw_events:
            lines.append(f"  event: {evt.get('event', '?')} | data: {evt.get('data', '')}")

        return "\n".join(lines)


def parse_sse_lines(raw: str) -> list[dict]:
    """Parse raw SSE text into a list of ``{event, data}`` dicts."""
    events = []
    current_event = None
    current_data_parts = []

    for line in raw.split("\n"):
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current_data_parts.append(line[len("data:"):].strip())
        elif line.strip() == "" and current_event is not None:
            data_str = "\n".join(current_data_parts)
            events.append({"event": current_event, "data": data_str})
            current_event = None
            current_data_parts = []
        elif line.strip() == "" and current_data_parts:
            data_str = "\n".join(current_data_parts)
            events.append({"event": "message", "data": data_str})
            current_data_parts = []

    if current_event is not None and current_data_parts:
        data_str = "\n".join(current_data_parts)
        events.append({"event": current_event, "data": data_str})

    return events


def build_chat_result(raw_text: str, elapsed_ms: int) -> ChatResult:
    """Parse raw SSE text into a ``ChatResult``."""
    events = parse_sse_lines(raw_text)
    result = ChatResult(elapsed_ms=elapsed_ms, raw_events=events)

    text_parts = []
    for evt in events:
        etype = evt["event"]
        try:
            data = json.loads(evt["data"]) if evt["data"] else {}
        except json.JSONDecodeError:
            data = {"raw": evt["data"]}

        if etype == "token":
            text_parts.append(data.get("text", ""))
        elif etype == "card":
            result.cards.append(data)
        elif etype == "emergency":
            result.emergency = data
        elif etype == "__debug__":
            result.trace = data
        elif etype == "done":
            result.session_id = data.get("session_id")

    result.text = "".join(text_parts)
    return result


class AgentHarnessClient:
    """HTTP/SSE client for running CozyPup agent interactions from tools."""

    def __init__(self, base_url: str, debug: bool = False):
        self.base_url = base_url.rstrip("/")
        self.api = f"{self.base_url}/api/v1"
        self.token: str | None = None
        self.user_id: str | None = None
        self.email: str | None = None
        self.last_session_id: str | None = None
        self.debug = debug
        self._client = httpx.AsyncClient(timeout=TIMEOUT)

    @property
    def headers(self) -> dict:
        assert self.token, "Not authenticated - call auth_dev() first"
        return {"Authorization": f"Bearer {self.token}"}

    async def close(self):
        await self._client.aclose()

    async def auth_dev(self, email: str | None = None):
        email = email or f"harness-{uuid4()}@test.cozypup.app"
        for attempt in range(3):
            try:
                resp = await self._client.post(
                    f"{self.api}/auth/dev",
                    json={"name": "Harness User", "email": email},
                )
                break
            except httpx.TransportError:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))
        resp.raise_for_status()
        data = resp.json()
        self.token = data["access_token"]
        self.user_id = data.get("user_id")
        self.email = email

    async def chat(
        self,
        message: str,
        session_id: str | None = None,
        location: dict | None = None,
        language: str | None = None,
        images: list[str] | None = None,
    ) -> ChatResult:
        body: dict = {"message": message}
        if session_id or self.last_session_id:
            body["session_id"] = session_id or self.last_session_id
        if location:
            body["location"] = location
        if language:
            body["language"] = language
        if images:
            body["images"] = images

        start = time.monotonic()
        try:
            raw_parts = []
            req_headers = {**self.headers, "Accept": "text/event-stream"}
            if self.debug:
                req_headers["X-Debug"] = "true"
            async with self._client.stream(
                "POST",
                f"{self.api}/chat",
                json=body,
                headers=req_headers,
                timeout=TIMEOUT,
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_text():
                    raw_parts.append(chunk)

            elapsed = int((time.monotonic() - start) * 1000)
            result = build_chat_result("".join(raw_parts), elapsed)
            if result.session_id:
                self.last_session_id = result.session_id
            return result
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return ChatResult(elapsed_ms=elapsed, error=f"{type(exc).__name__}: {exc}")

    async def chat_sequence(self, messages: list[str], **kwargs) -> list[ChatResult]:
        results = []
        for msg in messages:
            results.append(await self.chat(msg, **kwargs))
        return results

    async def get_pets(self) -> list[dict]:
        resp = await self._client.get(f"{self.api}/pets", headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    async def get_events(
        self,
        date_str: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        if date_str:
            start_date = date_str
            end_date = date_str
        if not start_date:
            today = date.today()
            start_date = (today - timedelta(days=30)).isoformat()
            end_date = (today + timedelta(days=30)).isoformat()
        resp = await self._client.get(
            f"{self.api}/calendar",
            params={"start_date": start_date, "end_date": end_date},
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def create_pet(self, name: str, species: str = "dog") -> dict:
        resp = await self._client.post(
            f"{self.api}/pets",
            json={"name": name, "species": species},
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def create_event(
        self,
        *,
        pet_id: str,
        event_date: str,
        title: str,
        category: str = "daily",
        raw_text: str = "",
    ) -> dict:
        resp = await self._client.post(
            f"{self.api}/calendar",
            json={
                "pet_id": pet_id,
                "event_date": event_date,
                "title": title,
                "category": category,
                "raw_text": raw_text,
            },
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def confirm_action(self, action_id: str) -> dict:
        resp = await self._client.post(
            f"{self.api}/chat/confirm-action",
            json={"action_id": action_id},
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def create_share_token(self, pet_id: str) -> dict:
        resp = await self._client.post(f"{self.api}/pets/{pet_id}/share-token", headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    async def accept_share(self, token: str, merge_pet_id: str | None = None) -> dict:
        body: dict = {"token": token}
        if merge_pet_id:
            body["merge_pet_id"] = merge_pet_id
        resp = await self._client.post(f"{self.api}/pets/accept-share", json=body, headers=self.headers)
        return {"status_code": resp.status_code, **resp.json()}

    async def unshare_pet(self, pet_id: str, keep_copy: bool = False) -> dict:
        resp = await self._client.post(
            f"{self.api}/pets/{pet_id}/unshare",
            json={"keep_copy": keep_copy},
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def set_subscription(self, status: str = "active", product_id: str | None = None) -> dict:
        body: dict = {"status": status}
        if product_id is not None:
            body["product_id"] = product_id
        resp = await self._client.post(
            f"{self.api}/auth/dev/set-subscription",
            json=body,
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_family_status(self) -> dict:
        resp = await self._client.get(f"{self.api}/family/status", headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    async def invite_family(self, email: str) -> dict:
        resp = await self._client.post(f"{self.api}/family/invite", json={"email": email}, headers=self.headers)
        return {"status_code": resp.status_code, **resp.json()}

    async def accept_family(self, invite_id: str | None = None) -> dict:
        body: dict = {}
        if invite_id:
            body["invite_id"] = invite_id
        resp = await self._client.post(f"{self.api}/family/accept", json=body, headers=self.headers)
        return {"status_code": resp.status_code, **resp.json()}

    async def revoke_family(self) -> dict:
        resp = await self._client.post(f"{self.api}/family/revoke", headers=self.headers)
        return {"status_code": resp.status_code, **resp.json()}

    async def get_tasks_today(self) -> list[dict]:
        resp = await self._client.get(f"{self.api}/tasks/today", headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    async def get_reminders(self) -> list[dict]:
        resp = await self._client.get(f"{self.api}/reminders", headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def dump_failure(
        self,
        test_id: str,
        lang: str,
        result: ChatResult,
        expected: str,
        actual: str,
        extra_context: str = "",
        directory: Path | None = None,
    ) -> Path:
        out_dir = directory or Path("reports") / "failures"
        out_dir.mkdir(parents=True, exist_ok=True)
        filepath = out_dir / f"{test_id}_{lang}.log"
        lines = [
            f"=== Test failed: {test_id} ({lang}) ===",
            f"elapsed: {result.elapsed_ms}ms",
            "",
            result.dump(),
            "",
            "-- Expected vs actual --",
            f"expected: {expected}",
            f"actual: {actual}",
        ]
        if extra_context:
            lines.extend(["", "-- Extra context --", extra_context])
        filepath.write_text("\n".join(lines), encoding="utf-8")
        return filepath


def has_cjk(text: str) -> bool:
    for ch in text:
        cp = ord(ch)
        if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or 0xF900 <= cp <= 0xFAFF:
            return True
    return False


def today_str() -> str:
    return date.today().isoformat()


def yesterday_str() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


def load_test_image(path: str | None = None) -> str:
    if path is not None:
        project_root = Path(__file__).resolve().parents[2]
        img_path = project_root / path
        return base64.b64encode(img_path.read_bytes()).decode()

    mini_jpeg = bytes([
        0xFF, 0xD8,
        0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46,
        0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01,
        0x00, 0x00,
        0xFF, 0xDB, 0x00, 0x43, 0x00,
        *([0x01] * 64),
        0xFF, 0xC0, 0x00, 0x0B, 0x08,
        0x00, 0x01, 0x00, 0x01, 0x01, 0x01, 0x11, 0x00,
        0xFF, 0xC4, 0x00, 0x1F, 0x00,
        0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01,
        0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
        0x08, 0x09, 0x0A, 0x0B,
        0xFF, 0xC4, 0x00, 0xB5, 0x10,
        0x00, 0x02, 0x01, 0x03, 0x03, 0x02, 0x04, 0x03,
        0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12,
        0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07,
        0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0,
        0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16,
        0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39,
        0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
        0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
        0x6A, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79,
        0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98,
        0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7,
        0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5,
        0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4,
        0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA,
        0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8,
        0xF9, 0xFA,
        0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00,
        0x3F, 0x00, 0x7B, 0x40,
        0xFF, 0xD9,
    ])
    return base64.b64encode(mini_jpeg).decode()


def get_tools_called(result: ChatResult) -> list[str]:
    if not result.trace:
        return []

    tools: list[str] = []

    def add_tool(name: str | None) -> None:
        if name and name not in tools:
            tools.append(str(name))

    events = result.trace.get("events", [])
    for event in events:
        if not isinstance(event, dict):
            continue
        data = event.get("data", {})
        if not isinstance(data, dict):
            continue
        tc = data.get("tools_called")
        if tc is not None:
            for tool in tc:
                add_tool(str(tool))
        if event.get("type") == "tool_call_started":
            add_tool(data.get("tool") or data.get("name"))

    steps = result.trace.get("steps", [])
    for step in steps:
        if not isinstance(step, dict):
            continue
        inner = step.get("data", {})
        if not isinstance(inner, dict):
            continue
        tc = inner.get("tools_called")
        if tc is not None:
            for tool in tc:
                add_tool(str(tool))
        add_tool(inner.get("tool") or inner.get("name"))
    return tools


# Back-compat aliases for old tests that imported private helpers.
E2EClient = AgentHarnessClient
_parse_sse_lines = parse_sse_lines
_build_chat_result = build_chat_result
