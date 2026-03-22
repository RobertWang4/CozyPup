"""Chat Agent — handles general conversation with function calling for calendar operations."""

import json
import logging
import re
from typing import Callable, Optional

import litellm

from app.agents.base import BaseAgent
from app.agents.prompts import CHAT_SYSTEM_PROMPT
from app.agents.tools import TOOL_DEFINITIONS, execute_tool
from app.agents.validation import validate_tool_args
from app.config import settings

logger = logging.getLogger(__name__)

# Maximum rounds of tool calls before forcing a text response
MAX_TOOL_ROUNDS = 5

# Patterns that indicate the LLM claimed to perform an action without actually
# calling a tool.
_SHOULD_HAVE_ACTED = re.compile(
    r"已记录|已更新|已保存|已添加|已设置|记住了|帮你记|帮你添加|帮你设"
    r"|I'?ve recorded|I'?ve updated|I'?ve saved|I'?ve added|I'?ve set"
    r"|I recorded|I updated|I saved|I added|I created"
    r"|recorded it|saved it|added it|updated it|created it",
    re.IGNORECASE,
)


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
                - is_emergency (bool): Whether emergency keywords were detected.
            on_token: Callback for streaming text tokens — on_token(text: str).
            on_card: Callback for card events — on_card(card_data: dict).

        Returns:
            dict with keys: response (str), intent ("chat"), cards (list[dict]).
        """
        db = context["db"]
        user_id = context["user_id"]
        location = context.get("location")
        system_prompt = context.get("system_prompt", CHAT_SYSTEM_PROMPT)

        # Model routing: emergency → Kimi K2.5, normal → Qwen
        is_emergency = context.get("is_emergency", False)
        model = settings.emergency_model if is_emergency else settings.default_model
        logger.info("model_selected", extra={"model": model, "is_emergency": is_emergency})

        # Build message history
        context_messages = context.get("context_messages", [])
        messages = [
            {"role": "system", "content": system_prompt},
            *context_messages,
            {"role": "user", "content": message},
        ]

        full_response = ""
        cards: list[dict] = []
        any_tool_called = False

        for _round in range(MAX_TOOL_ROUNDS):
            # Stream the LLM response
            response_text, tool_calls = await self._stream_completion(
                messages, model=model, on_token=on_token
            )

            full_response += response_text

            if not tool_calls:
                # No tool calls — we're done
                break

            any_tool_called = True

            # Process tool calls
            # Add assistant message with tool calls to conversation
            assistant_msg = {"role": "assistant", "content": response_text or None, "tool_calls": tool_calls}
            messages.append(assistant_msg)

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError as exc:
                    logger.warning("tool_args_json_error", extra={"tool": fn_name, "error": str(exc)[:200]})
                    result = {"error": f"Invalid JSON in arguments: {exc}"}
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    })
                    continue

                logger.info(
                    "chat_agent_tool_call",
                    extra={"tool": fn_name, "round": _round},
                )

                # Schema validation — errors go back to LLM for retry
                validation_errors = validate_tool_args(fn_name, fn_args)
                if validation_errors:
                    logger.warning(
                        "tool_validation_failed",
                        extra={"tool": fn_name, "errors": validation_errors},
                    )
                    result = {"error": "Validation failed: " + "; ".join(validation_errors)}
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    })
                    continue

                try:
                    result = await execute_tool(fn_name, fn_args, db, user_id, location=location)

                    # Commit immediately so data is persisted before the card
                    # is sent to the frontend. This ensures card display and
                    # database write are always in sync — if the user sees a
                    # card, the data is guaranteed to be in the database.
                    await db.commit()

                    if "card" in result:
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

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result),
                })

        # --- Post-check: detect hallucinated actions or "which pet?" ---
        if not any_tool_called and _SHOULD_HAVE_ACTED.search(full_response):
            logger.warning(
                "should_have_acted_detected",
                extra={"response_snippet": full_response[:200]},
            )
            retry_text, retry_cards = await self._retry_with_forced_tool(
                messages, model=model, db=db, user_id=user_id,
                location=location, on_token=on_token, on_card=on_card,
            )
            if retry_cards:
                full_response = retry_text
                cards = retry_cards

        return {
            "response": full_response,
            "intent": "chat",
            "cards": cards,
        }

    async def _retry_with_forced_tool(
        self,
        messages: list[dict],
        model: str,
        db,
        user_id,
        location=None,
        on_token: Optional[Callable] = None,
        on_card: Optional[Callable] = None,
    ) -> tuple[str, list[dict]]:
        """Retry with tool_choice=required when post-check detects the LLM
        claimed an action or asked "which pet?" without calling a tool."""
        retry_messages = list(messages) + [
            {
                "role": "user",
                "content": (
                    "You MUST call a tool NOW. Do NOT ask which pet — "
                    "if unsure, call the tool once for EACH pet. Act immediately."
                ),
            }
        ]

        response_text, tool_calls = await self._stream_completion(
            retry_messages, model=model, on_token=on_token, tool_choice="required",
        )

        cards: list[dict] = []
        if not tool_calls:
            return response_text, cards

        assistant_msg = {"role": "assistant", "content": response_text or None, "tool_calls": tool_calls}
        retry_messages.append(assistant_msg)

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                continue

            validation_errors = validate_tool_args(fn_name, fn_args)
            if validation_errors:
                continue

            try:
                result = await execute_tool(fn_name, fn_args, db, user_id, location=location)
                await db.commit()
                if "card" in result:
                    cards.append(result["card"])
                    if on_card:
                        await _maybe_await(on_card, result["card"])
            except Exception as exc:
                logger.error("retry_tool_error", extra={"tool": fn_name, "error": str(exc)[:200]})

        if cards:
            for tc in tool_calls:
                retry_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps({"success": True}),
                })
            final_text, _ = await self._stream_completion(
                retry_messages, model=model, on_token=on_token,
            )
            return final_text, cards

        return response_text, cards

    async def _stream_completion(
        self,
        messages: list[dict],
        model: str | None = None,
        on_token: Optional[Callable] = None,
        tool_choice: str = "auto",
    ) -> tuple[str, list[dict]]:
        """Call LiteLLM with streaming and collect text + tool calls.

        Returns:
            (response_text, tool_calls) where tool_calls is a list of
            OpenAI-format tool call dicts.
        """
        model = model or settings.default_model

        # Build LiteLLM call kwargs
        completion_kwargs: dict = dict(
            model=model,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice=tool_choice,
            stream=True,
            temperature=0.3,
        )

        # Proxy credentials
        if settings.model_api_base:
            completion_kwargs["api_base"] = settings.model_api_base
        if settings.model_api_key:
            completion_kwargs["api_key"] = settings.model_api_key

        # Disable thinking/reasoning output for Qwen models
        if "qwen" in model.lower():
            completion_kwargs["extra_body"] = {"enable_thinking": False}

        response = await litellm.acompletion(**completion_kwargs)

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
