"""E2E test infrastructure — simulates a real iOS user hitting the backend API.

Each test module gets an isolated dev user. Tests verify tool calls, card types,
card fields, and API side effects. SSE parsing replicates iOS ChatService.swift.
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio

from app.agent_harness.client import (
    AgentHarnessClient as E2EClient,
    ChatResult,
    _build_chat_result,
    _parse_sse_lines,
    get_tools_called,
    has_cjk,
    load_test_image,
    today_str,
    yesterday_str,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")


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
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def e2e(base_url):
    """Create an isolated E2E client with a fresh dev user."""
    client = E2EClient(base_url)
    await client.auth_dev()
    client.last_session_id = None  # force new session
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


# ---------------------------------------------------------------------------
# Debug-enabled fixtures (X-Debug: true → trace data available)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def e2e_debug(base_url):
    """E2E client with debug=True for trace inspection."""
    client = E2EClient(base_url, debug=True)
    await client.auth_dev()
    client.last_session_id = None  # force new session
    yield client
    await client.close()


@pytest_asyncio.fixture
async def e2e_debug_with_pet(e2e_debug):
    """Debug E2E client with one pre-created pet named '小维' (dog)."""
    pet = await e2e_debug.create_pet("小维", "dog")
    e2e_debug._default_pet = pet
    return e2e_debug


@pytest_asyncio.fixture
async def e2e_debug_with_two_pets(e2e_debug):
    """Debug E2E client with two pets: 小维 (dog) + 花花 (cat)."""
    pet1 = await e2e_debug.create_pet("小维", "dog")
    pet2 = await e2e_debug.create_pet("花花", "cat")
    e2e_debug._pets = [pet1, pet2]
    return e2e_debug


@pytest_asyncio.fixture
async def e2e_debug_with_three_pets(e2e_debug):
    """Debug E2E client with three pets: 小维 (dog), 花花 (cat), 豆豆 (dog)."""
    pet1 = await e2e_debug.create_pet("小维", "dog")
    pet2 = await e2e_debug.create_pet("花花", "cat")
    pet3 = await e2e_debug.create_pet("豆豆", "dog")
    e2e_debug._pets = [pet1, pet2, pet3]
    return e2e_debug


# ---------------------------------------------------------------------------
# Pair fixture (two isolated users for sharing / family tests)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def e2e_pair(base_url):
    """Two isolated debug-enabled E2E clients (A and B) for sharing/family tests."""
    a = E2EClient(base_url, debug=True)
    b = E2EClient(base_url, debug=True)
    await a.auth_dev()
    await b.auth_dev()
    yield a, b
    await a.close()
    await b.close()
