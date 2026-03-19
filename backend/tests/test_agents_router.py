"""Tests for the LLM intent router."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.router import route_intent


def _make_litellm_response(content: str):
    """Build a mock LiteLLM completion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.mark.asyncio
class TestRouteIntent:
    """Test intent routing with mocked LiteLLM."""

    @patch("app.agents.router.litellm")
    async def test_routes_chat_intent(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response('{"intent": "chat"}')
        )
        result = await route_intent("How much should I feed my dog?", [])
        assert result == "chat"

    @patch("app.agents.router.litellm")
    async def test_routes_summarize_intent(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response('{"intent": "summarize"}')
        )
        result = await route_intent("Summarize today's chat", [])
        assert result == "summarize"

    @patch("app.agents.router.litellm")
    async def test_routes_map_intent(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response('{"intent": "map"}')
        )
        result = await route_intent("Find a vet near me", [])
        assert result == "map"

    @patch("app.agents.router.litellm")
    async def test_routes_email_intent(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response('{"intent": "email"}')
        )
        result = await route_intent("Write an email to my vet", [])
        assert result == "email"

    @patch("app.agents.router.litellm")
    async def test_fallback_on_invalid_intent(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response('{"intent": "unknown_thing"}')
        )
        result = await route_intent("Do something weird", [])
        assert result == "chat"

    @patch("app.agents.router.litellm")
    async def test_fallback_on_invalid_json(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response("not json at all")
        )
        result = await route_intent("Hello", [])
        assert result == "chat"

    @patch("app.agents.router.litellm")
    async def test_fallback_on_exception(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(side_effect=Exception("API down"))
        result = await route_intent("Hello", [])
        assert result == "chat"

    @patch("app.agents.router.litellm")
    async def test_passes_context_messages(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response('{"intent": "chat"}')
        )
        context = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        await route_intent("Thanks", context)

        # Verify the LLM was called with system + context + current message
        call_args = mock_litellm.acompletion.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1] == {"role": "user", "content": "Hi"}
        assert messages[2] == {"role": "assistant", "content": "Hello!"}
        assert messages[3] == {"role": "user", "content": "Thanks"}

    @patch("app.agents.router.litellm")
    async def test_limits_context_to_10(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response('{"intent": "chat"}')
        )
        # Create 20 context messages
        context = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        await route_intent("Latest", context)

        call_args = mock_litellm.acompletion.call_args
        messages = call_args.kwargs["messages"]
        # 1 system + 10 context (last 10) + 1 current = 12
        assert len(messages) == 12

    @patch("app.agents.router.litellm")
    async def test_handles_json_with_whitespace(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response('  {"intent": "map"}  \n')
        )
        result = await route_intent("Where is the nearest pet store?", [])
        assert result == "map"
