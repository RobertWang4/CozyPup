"""E2E test infrastructure — simulates a real iOS user hitting the backend API.

Each test module gets an isolated dev user. Tests verify tool calls, card types,
card fields, and API side effects. SSE parsing replicates iOS ChatService.swift.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")
API = f"{BASE_URL}/api/v1"
TIMEOUT = 120.0  # LLM responses can be slow (SSE streaming with tool calls)

REPORTS_DIR = Path(__file__).parent / "reports"
FAILURES_DIR = REPORTS_DIR / "failures"
REPORTS_DIR.mkdir(exist_ok=True)
FAILURES_DIR.mkdir(exist_ok=True)


def pytest_addoption(parser):
    parser.addoption(
        "--e2e-base-url",
        default=BASE_URL,
        help="Base URL of the CozyPup backend server",
    )


@pytest.fixture(scope="session")
def base_url(request):
    return request.config.getoption("--e2e-base-url")


# ---------------------------------------------------------------------------
# ChatResult — structured SSE response
# ---------------------------------------------------------------------------

@dataclass
class ChatResult:
    """Structured result from a single chat SSE request."""

    text: str = ""
    cards: list[dict] = field(default_factory=list)
    emergency: dict | None = None
    session_id: str | None = None
    raw_events: list[dict] = field(default_factory=list)
    elapsed_ms: int = 0
    error: str | None = None
    trace: dict | None = None  # Debug trace data (when X-Debug: true)

    # -- Card helpers --

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

    # -- Dump for failure logs --

    def dump(self) -> str:
        lines = []
        lines.append(f"── LLM 回复 ({self.elapsed_ms}ms) ──")
        lines.append(self.text or "(空)")
        lines.append("")

        if self.cards:
            lines.append(f"── 收到的卡片 ({len(self.cards)}) ──")
            for i, c in enumerate(self.cards):
                lines.append(f"  [{i}] {json.dumps(c, ensure_ascii=False, indent=2)}")
        else:
            lines.append("── 收到的卡片 ──\n(无)")
        lines.append("")

        if self.emergency:
            lines.append(f"── Emergency ──\n{json.dumps(self.emergency, ensure_ascii=False)}")
            lines.append("")

        if self.error:
            lines.append(f"── 错误 ──\n{self.error}")
            lines.append("")

        lines.append("── 原始 SSE 事件流 ──")
        for evt in self.raw_events:
            lines.append(f"  event: {evt.get('event', '?')} | data: {evt.get('data', '')}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# SSE Parser
# ---------------------------------------------------------------------------

def _parse_sse_lines(raw: str) -> list[dict]:
    """Parse raw SSE text into list of {event, data} dicts."""
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
            # data-only event (no event: line)
            data_str = "\n".join(current_data_parts)
            events.append({"event": "message", "data": data_str})
            current_data_parts = []

    # Handle trailing event without final newline
    if current_event is not None and current_data_parts:
        data_str = "\n".join(current_data_parts)
        events.append({"event": current_event, "data": data_str})

    return events


def _build_chat_result(raw_text: str, elapsed_ms: int) -> ChatResult:
    """Parse raw SSE text into a ChatResult."""
    events = _parse_sse_lines(raw_text)
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


# ---------------------------------------------------------------------------
# E2EClient — one per test module, simulates a real user
# ---------------------------------------------------------------------------

class E2EClient:
    """Simulates a real iOS user hitting the CozyPup API."""

    def __init__(self, base_url: str, debug: bool = False):
        self.base_url = base_url.rstrip("/")
        self.api = f"{self.base_url}/api/v1"
        self.token: str | None = None
        self.user_id: str | None = None
        self.last_session_id: str | None = None
        self.debug = debug  # Send X-Debug: true header
        self._client = httpx.AsyncClient(timeout=TIMEOUT)

    @property
    def headers(self) -> dict:
        assert self.token, "Not authenticated — call auth_dev() first"
        return {"Authorization": f"Bearer {self.token}"}

    async def close(self):
        await self._client.aclose()

    # -- Auth --

    async def auth_dev(self, email: str | None = None):
        """Authenticate as a dev user (creates a fresh user)."""
        email = email or f"e2e-{uuid4()}@test.cozypup.app"
        resp = await self._client.post(
            f"{self.api}/auth/dev",
            json={"name": "E2E Test User", "email": email},
        )
        resp.raise_for_status()
        data = resp.json()
        self.token = data["access_token"]
        self.user_id = data.get("user_id")

    # -- Chat (SSE) --

    async def chat(
        self,
        message: str,
        session_id: str | None = None,
        location: dict | None = None,
        language: str | None = None,
        images: list[str] | None = None,
    ) -> ChatResult:
        """Send a chat message and parse SSE response. Core test method."""
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
            # Use streaming to handle SSE
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
            raw = "".join(raw_parts)
            result = _build_chat_result(raw, elapsed)
            if result.session_id:
                self.last_session_id = result.session_id
            return result

        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return ChatResult(
                elapsed_ms=elapsed,
                error=f"{type(exc).__name__}: {exc}",
            )

    async def chat_sequence(self, messages: list[str], **kwargs) -> list[ChatResult]:
        """Send multiple messages in sequence (same session)."""
        results = []
        for msg in messages:
            r = await self.chat(msg, **kwargs)
            results.append(r)
        return results

    # -- API helpers for side-effect verification --

    async def get_pets(self) -> list[dict]:
        """GET /pets — verify pet side effects."""
        resp = await self._client.get(f"{self.api}/pets", headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    async def get_events(
        self,
        date_str: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """GET /calendar — verify calendar side effects."""
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
        """POST /pets — create a pet directly via API (for test setup)."""
        resp = await self._client.post(
            f"{self.api}/pets",
            json={"name": name, "species": species},
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def confirm_action(self, action_id: str) -> dict:
        """POST /chat/confirm-action — confirm a destructive operation."""
        resp = await self._client.post(
            f"{self.api}/chat/confirm-action",
            json={"action_id": action_id},
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    # -- Failure logging --

    def dump_failure(
        self,
        test_id: str,
        lang: str,
        result: ChatResult,
        expected: str,
        actual: str,
        extra_context: str = "",
    ):
        """Write a detailed failure log to reports/failures/."""
        filename = f"{test_id}_{lang}.log"
        filepath = FAILURES_DIR / filename

        lines = [
            f"═══ 测试失败：{test_id} ({lang}) ═══",
            f"耗时: {result.elapsed_ms}ms",
            "",
            result.dump(),
            "",
            "── 预期 vs 实际 ──",
            f"预期: {expected}",
            f"实际: {actual}",
        ]
        if extra_context:
            lines.extend(["", "── 补充信息 ──", extra_context])

        filepath.write_text("\n".join(lines), encoding="utf-8")
        return filepath


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

def has_cjk(text: str) -> bool:
    """Check if text contains CJK characters."""
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF or    # CJK Unified Ideographs
            0x3400 <= cp <= 0x4DBF or     # CJK Extension A
            0xF900 <= cp <= 0xFAFF):      # CJK Compatibility
            return True
    return False


def today_str() -> str:
    return date.today().isoformat()


def yesterday_str() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def e2e(base_url):
    """Create an isolated E2E client with a fresh dev user."""
    client = E2EClient(base_url)
    await client.auth_dev()
    yield client
    await client.close()


@pytest_asyncio.fixture
async def e2e_with_pet(e2e):
    """E2E client with one pre-created pet named '小维' (Weiwei)."""
    pet = await e2e.create_pet("小维", "dog")
    e2e._default_pet = pet
    return e2e


@pytest_asyncio.fixture
async def e2e_with_two_pets(e2e):
    """E2E client with two pets for multi-pet tests."""
    pet1 = await e2e.create_pet("小维", "dog")
    pet2 = await e2e.create_pet("花花", "cat")
    e2e._pets = [pet1, pet2]
    return e2e
