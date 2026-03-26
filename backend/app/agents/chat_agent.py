"""Chat Agent — handles general conversation with function calling for calendar operations."""

import base64
import json
import logging
import uuid as _uuid
from pathlib import Path
from typing import Callable, Optional

import litellm

from app.agents.base import BaseAgent
from app.agents.locale import t
from app.agents.pending_actions import store_action
from app.agents.post_processor import execute_suggested_actions, response_claims_action
from app.agents.pre_processor import SuggestedAction, format_actions_for_prompt, pre_process
from app.agents.prompts import CHAT_SYSTEM_PROMPT
from app.agents.tools import TOOL_DEFINITIONS, execute_tool, get_tool_definitions
from app.agents.validation import validate_tool_args
from app.config import settings

logger = logging.getLogger(__name__)

# Maximum rounds of tool calls before forcing a text response
MAX_TOOL_ROUNDS = 5

# Only destructive tools require user confirmation via confirm card.
# Everything else the LLM decides to call executes immediately.
CONFIRM_TOOLS = {"delete_pet", "delete_calendar_event", "delete_reminder"}


def _describe_tool_call(fn_name: str, fn_args: dict, pets: list | None = None, lang: str = "zh") -> str:
    """Generate human-readable description from LLM's tool call arguments."""
    def _pet_name(pid: str) -> str:
        if not pets:
            return ""
        for p in pets:
            if str(p.id if hasattr(p, "id") else p.get("id", "")) == pid:
                return p.name if hasattr(p, "name") else p.get("name", "")
        return ""

    pid = fn_args.get("pet_id", "")
    name = _pet_name(pid)
    label = f"「{name}」" if name else ""

    if fn_name == "update_pet_profile":
        info = fn_args.get("info", {})
        if "name" in info:
            return t("desc_rename", lang).format(label=label, name=info['name'])
        keys = ", ".join(info.keys())
        return t("desc_update_pet", lang).format(label=label, keys=keys)
    if fn_name == "create_pet":
        return t("desc_create_pet", lang).format(name=fn_args.get('name', ''))
    if fn_name == "delete_pet":
        return t("desc_delete_pet", lang).format(label=label)
    if fn_name == "create_calendar_event":
        title = fn_args.get("title", "")
        d = fn_args.get("event_date", "")
        return t("desc_create_event", lang).format(title=title, date=d)
    if fn_name == "update_calendar_event":
        return t("desc_update_event", lang)
    if fn_name == "delete_calendar_event":
        return t("desc_delete_event", lang)
    if fn_name == "create_reminder":
        return t("desc_create_reminder", lang).format(title=fn_args.get('title', ''))
    if fn_name == "update_reminder":
        return t("desc_update_reminder", lang)
    if fn_name == "delete_reminder":
        return t("desc_delete_reminder", lang)
    if fn_name == "draft_email":
        return t("desc_draft_email", lang).format(subject=fn_args.get('subject', ''))
    if fn_name == "save_pet_profile_md":
        return t("desc_save_profile", lang).format(label=label)
    if fn_name == "set_pet_avatar":
        return t("desc_set_avatar", lang).format(label=label)
    if fn_name == "upload_event_photo":
        return t("desc_upload_photo", lang)
    return fn_name


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
                - pets (list[Pet]): Raw pet model instances.
            on_token: Callback for streaming text tokens — on_token(text: str).
            on_card: Callback for card events — on_card(card_data: dict).

        Returns:
            dict with keys: response (str), intent ("chat"), cards (list[dict]).
        """
        db = context["db"]
        user_id = context["user_id"]
        session_id = context.get("session_id")
        location = context.get("location")
        system_prompt = context.get("system_prompt", CHAT_SYSTEM_PROMPT)
        pets = context.get("pets", [])
        lang = context.get("lang", "zh")
        self._lang = lang  # store for _stream_completion

        # --- Phase 0: Deterministic pre-processing ---
        suggested_actions = pre_process(message, pets)
        actions_prompt = format_actions_for_prompt(suggested_actions)

        # Inject pre-analyzed actions into system prompt
        if actions_prompt:
            system_prompt = system_prompt.replace("{pre_analyzed_actions}", actions_prompt)
        else:
            system_prompt = system_prompt.replace("{pre_analyzed_actions}", "")

        # Model routing: emergency → Kimi K2.5, normal → Qwen
        is_emergency = context.get("is_emergency", False)
        model = settings.emergency_model if is_emergency else settings.default_model
        logger.info("model_selected", extra={
            "model": model,
            "is_emergency": is_emergency,
            "suggested_actions": len(suggested_actions),
        })

        # Hints are advisory — LLM always decides via tool_choice="auto"
        tool_choice = "auto"

        # Build message history
        context_messages = context.get("context_messages", [])
        images = context.get("images") or []

        # Build user message — multimodal if images present
        if images:
            user_content: list[dict] = [{"type": "text", "text": message}]
            for img_b64 in images:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                })
            user_msg = {"role": "user", "content": user_content}
        else:
            user_msg = {"role": "user", "content": message}

        messages = [
            {"role": "system", "content": system_prompt},
            *context_messages,
            user_msg,
        ]

        full_response = ""
        cards: list[dict] = []
        any_tool_called = False
        has_confirm_card = False

        # --- Phase 1: Streaming LLM call with tool execution ---
        for _round in range(MAX_TOOL_ROUNDS):
            response_text, tool_calls = await self._stream_completion(
                messages, model=model, on_token=on_token,
                tool_choice=tool_choice if _round == 0 else "auto",
            )

            full_response += response_text

            if not tool_calls:
                break

            any_tool_called = True

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
                    extra={"tool": fn_name, "round": _round, "arguments": fn_args},
                )

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

                # --- Confirm gate: only for destructive operations ---
                if fn_name in CONFIRM_TOOLS and session_id:
                    description = _describe_tool_call(fn_name, fn_args, pets, lang=lang)
                    action_id = store_action(
                        user_id=str(user_id),
                        session_id=str(session_id),
                        tool_name=fn_name,
                        arguments=fn_args,
                        description=description,
                    )
                    confirm_card = {
                        "type": "confirm_action",
                        "action_id": action_id,
                        "message": description,
                    }
                    cards.append(confirm_card)
                    if on_card:
                        await _maybe_await(on_card, confirm_card)
                    has_confirm_card = True

                    # Tell the LLM it's pending confirmation (so it doesn't say "已完成")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps({
                            "status": "pending_user_confirmation",
                            "message": t("confirm_pending", lang),
                        }),
                    })
                    continue

                # --- Normal execution for non-confirm tools ---
                try:
                    result = await execute_tool(fn_name, fn_args, db, user_id, location=location, images=images)
                    await db.commit()

                    # Tool returned needs_confirm (e.g. gender/species first-time set)
                    if result.get("needs_confirm") and session_id:
                        confirm_tool = result.get("confirm_tool", fn_name)
                        confirm_args = result.get("confirm_arguments", fn_args)
                        confirm_desc = result.get("confirm_description", f"确认执行 {fn_name}")
                        action_id = store_action(
                            user_id=str(user_id),
                            session_id=str(session_id),
                            tool_name=confirm_tool,
                            arguments=confirm_args,
                            description=confirm_desc,
                        )
                        confirm_card = {
                            "type": "confirm_action",
                            "action_id": action_id,
                            "message": confirm_desc,
                        }
                        cards.append(confirm_card)
                        if on_card:
                            await _maybe_await(on_card, confirm_card)
                        has_confirm_card = True

                        # Tell the LLM it's pending confirmation
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps({
                                "status": "pending_user_confirmation",
                                "message": confirm_desc,
                            }),
                        })
                        continue

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

            # If we emitted confirm cards and no other tools need execution,
            # skip the follow-up LLM call (no need for "已完成" text)
            if has_confirm_card:
                break

        # --- Phase 2: Deterministic post-check ---
        # If LLM claimed an action but didn't call any tool, execute
        # the pre-processor's suggested actions directly (no LLM retry).
        if not any_tool_called and suggested_actions and response_claims_action(full_response):
            logger.warning(
                "post_processor_triggered",
                extra={"response_snippet": full_response[:200], "actions": len(suggested_actions)},
            )
            fallback_cards = await execute_suggested_actions(
                suggested_actions, db, user_id, on_card=on_card, location=location,
            )
            cards.extend(fallback_cards)

        return {
            "response": full_response,
            "intent": "chat",
            "cards": cards,
        }

    async def _stream_completion(
        self,
        messages: list[dict],
        model: str | None = None,
        on_token: Optional[Callable] = None,
        tool_choice: str = "auto",
    ) -> tuple[str, list[dict]]:
        """Call LiteLLM with streaming and collect text + tool calls."""
        model = model or settings.default_model

        # Qwen streaming bug: enable_thinking=False is ignored in streaming mode,
        # so tool_choice=required fails. Workaround: when forcing tool calls on Qwen,
        # use a non-streaming call to extract tool calls, then stream the follow-up.
        is_qwen = "qwen" in (model or "").lower()
        force_non_stream = is_qwen and tool_choice == "required"

        lang = getattr(self, "_lang", "zh")
        tool_defs = get_tool_definitions(lang)

        completion_kwargs: dict = dict(
            model=model,
            messages=messages,
            tools=tool_defs,
            tool_choice=tool_choice,
            stream=not force_non_stream,
            temperature=0.3,
        )

        if settings.model_api_base:
            completion_kwargs["api_base"] = settings.model_api_base
        if settings.model_api_key:
            completion_kwargs["api_key"] = settings.model_api_key

        if is_qwen:
            completion_kwargs["extra_body"] = {"enable_thinking": False}

        response = await litellm.acompletion(**completion_kwargs)

        # Non-streaming path for Qwen + tool_choice=required
        if force_non_stream:
            msg = response.choices[0].message
            text = msg.content or ""
            tool_calls = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_dict = tc if isinstance(tc, dict) else {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    tool_calls.append(tc_dict)
            if text and on_token:
                await _maybe_await(on_token, text)
            return text, tool_calls

        text_parts: list[str] = []
        tool_calls_map: dict[int, dict] = {}

        async for chunk in response:
            delta = chunk.choices[0].delta

            if delta.content:
                text_parts.append(delta.content)
                if on_token:
                    await _maybe_await(on_token, delta.content)

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
