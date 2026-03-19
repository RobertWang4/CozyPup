"""Chat Agent — handles general conversation with function calling for calendar operations."""

import json
import logging
from typing import Callable, Optional

import litellm

from app.agents.base import BaseAgent
from app.agents.prompts import CHAT_SYSTEM_PROMPT
from app.agents.tools import TOOL_DEFINITIONS, execute_tool
from app.config import settings

logger = logging.getLogger(__name__)

# Maximum rounds of tool calls before forcing a text response
MAX_TOOL_ROUNDS = 5


class ChatAgent(BaseAgent):
    name = "chat_agent"

    async def _run(
        self,
        message: str,
        context: dict,
        on_token: Optional[Callable] = None,
        on_card: Optional[Callable] = None,
        **kwargs,
    ) -> dict:
        """Run the chat agent with streaming and function calling.

        Args:
            message: The user's message.
            context: Dict with keys:
                - system_prompt (str): Formatted system prompt with pet context.
                - context_messages (list[dict]): Recent conversation history.
                - db (AsyncSession): Database session for tool execution.
                - user_id (UUID): Authenticated user ID.
                - session_id (UUID): Current chat session ID.
            on_token: Callback for streaming text tokens — on_token(text: str).
            on_card: Callback for card events — on_card(card_data: dict).

        Returns:
            dict with keys: response (str), intent ("chat"), cards (list[dict]).
        """
        db = context["db"]
        user_id = context["user_id"]
        system_prompt = context.get("system_prompt", CHAT_SYSTEM_PROMPT)

        # Build message history
        context_messages = context.get("context_messages", [])
        messages = [
            {"role": "system", "content": system_prompt},
            *context_messages,
            {"role": "user", "content": message},
        ]

        full_response = ""
        cards: list[dict] = []

        for _round in range(MAX_TOOL_ROUNDS):
            # Stream the LLM response
            response_text, tool_calls = await self._stream_completion(
                messages, on_token=on_token
            )

            full_response += response_text

            if not tool_calls:
                # No tool calls — we're done
                break

            # Process tool calls
            # Add assistant message with tool calls to conversation
            assistant_msg = {"role": "assistant", "content": response_text or None, "tool_calls": tool_calls}
            messages.append(assistant_msg)

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])

                logger.info(
                    "chat_agent_tool_call",
                    extra={"tool": fn_name, "round": _round},
                )

                try:
                    result = await execute_tool(fn_name, fn_args, db, user_id)

                    # If it's a create event, emit a card
                    if fn_name == "create_calendar_event" and "card" in result:
                        card = result["card"]
                        cards.append(card)
                        if on_card:
                            await _maybe_await(on_card, card)

                except Exception as exc:
                    logger.error(
                        "chat_agent_tool_error",
                        extra={"tool": fn_name, "error": str(exc)[:200]},
                    )
                    result = {"error": str(exc)}

                # Add tool result to conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result),
                })

        return {
            "response": full_response,
            "intent": "chat",
            "cards": cards,
        }

    async def _stream_completion(
        self,
        messages: list[dict],
        on_token: Optional[Callable] = None,
    ) -> tuple[str, list[dict]]:
        """Call LiteLLM with streaming and collect text + tool calls.

        Returns:
            (response_text, tool_calls) where tool_calls is a list of
            OpenAI-format tool call dicts.
        """
        response = await litellm.acompletion(
            model=settings.strong_model,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            stream=True,
            temperature=0.7,
        )

        text_parts: list[str] = []
        tool_calls_map: dict[int, dict] = {}  # index -> tool call accumulator

        async for chunk in response:
            delta = chunk.choices[0].delta

            # Handle text content
            if delta.content:
                text_parts.append(delta.content)
                if on_token:
                    await _maybe_await(on_token, delta.content)

            # Handle tool calls (streamed incrementally)
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {
                            "id": tc_delta.id or "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    tc = tool_calls_map[idx]
                    if tc_delta.id:
                        tc["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tc["function"]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            tc["function"]["arguments"] += tc_delta.function.arguments

        response_text = "".join(text_parts)
        tool_calls = [tool_calls_map[i] for i in sorted(tool_calls_map)] if tool_calls_map else []

        return response_text, tool_calls


async def _maybe_await(fn: Callable, *args):
    """Call fn with args; if it returns a coroutine, await it."""
    import asyncio

    result = fn(*args)
    if asyncio.iscoroutine(result):
        await result
