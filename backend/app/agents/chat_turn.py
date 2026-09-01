"""Chat-turn input builders for the agent runtime.

This module owns the pure-ish preparation work before AgentEngine runs:
preprocessor hints, memory rendering, prompt construction, message shaping,
and image-reference selection. It deliberately does not execute tools, emit
SSE, or persist chat rows.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.emergency import EmergencyCheckResult, build_emergency_hint
from app.agents.pre_processing.types import SuggestedAction
from app.agents.prompts_v2 import build_messages, build_system_prompt
from app.config import settings
from app.memory.context_builder import build_memory_context
from app.memory.render import render_retrieved_context
from app.memory.types import RetrievedContext

RetrieveMemoryFn = Callable[..., Awaitable[RetrievedContext]]


@dataclass(frozen=True)
class AgentPromptInput:
    today: str
    model: str
    emergency_hint: str | None
    preprocessor_hints: list[str] = field(default_factory=list)
    retrieved_context: RetrievedContext = field(default_factory=RetrievedContext)
    memory_context: str = ""
    system_prompt: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    recent_image_urls: list[str] = field(default_factory=list)


def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def _role_value(role: Any) -> str:
    return role.value if hasattr(role, "value") else str(role)


def build_context_messages(context_messages: list[Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in context_messages:
        content = _get_attr(item, "content", "") or ""
        image_urls = _get_attr(item, "image_urls") or []
        if image_urls:
            count = len(image_urls)
            content += f"\n[附带了{count}张图片，如需查看可调用 request_images]"
        messages.append({
            "role": _role_value(_get_attr(item, "role", "user")),
            "content": content,
        })
    return messages


def recent_user_image_urls(context_messages: list[Any]) -> list[str]:
    for item in reversed(context_messages):
        role = _role_value(_get_attr(item, "role", ""))
        image_urls = _get_attr(item, "image_urls") or []
        if role == "user" and image_urls:
            return list(image_urls)
    return []


def build_preprocessor_hints(
    suggested_actions: list[SuggestedAction],
    *,
    is_first_message: bool,
    lang: str,
) -> list[str]:
    hints: list[str] = []
    for action in suggested_actions:
        if action.confidence >= 0.5:
            hints.append(
                f"{action.tool_name}({json.dumps(action.arguments, ensure_ascii=False)})"
            )

    if is_first_message:
        if lang == "zh":
            hints.append("introduce_product() — 这是新用户的第一条消息，先介绍产品功能")
        else:
            hints.append("introduce_product() — This is a new user's first message, introduce product features first")

    event_count = sum(
        1 for action in suggested_actions
        if action.tool_name == "create_calendar_event"
    )
    reminder_count = sum(
        1 for action in suggested_actions
        if action.tool_name == "create_reminder"
    )
    if event_count + reminder_count >= 2:
        if lang == "zh":
            hints.append("⚠️ 检测到多个事件/提醒意图，请确保每件事单独调用一次工具")
        else:
            hints.append("⚠️ Multiple events/reminders detected — make a separate tool call for each")

    return hints


def select_chat_model(
    *,
    is_emergency: bool,
    default_model: str | None = None,
    emergency_model: str | None = None,
) -> str:
    return (
        emergency_model or settings.emergency_model
        if is_emergency
        else default_model or settings.model
    )


async def build_agent_prompt_input(
    *,
    message: str,
    db: AsyncSession | object | None,
    user_id: uuid.UUID | None,
    pets: list[Any],
    session_summary: dict | None,
    context_messages: list[Any],
    emergency_result: EmergencyCheckResult,
    suggested_actions: list[SuggestedAction],
    lang: str,
    image_count: int,
    retrieve_memory_context: RetrieveMemoryFn = build_memory_context,
    default_model: str | None = None,
    emergency_model: str | None = None,
    today: str | None = None,
) -> AgentPromptInput:
    today_str = today or date.today().isoformat()
    is_emergency = emergency_result.detected
    emergency_hint = (
        build_emergency_hint(emergency_result.keywords, lang=lang)
        if is_emergency
        else None
    )
    preprocessor_hints = build_preprocessor_hints(
        suggested_actions,
        is_first_message=not context_messages and not session_summary,
        lang=lang,
    )
    retrieved_context = await retrieve_memory_context(
        message=message,
        db=db,
        user_id=user_id,
        pets=pets,
    )
    memory_context = render_retrieved_context(retrieved_context, lang=lang)
    system_prompt = build_system_prompt(
        pets=pets,
        session_summary=session_summary,
        memory_context=memory_context or None,
        emergency_hint=emergency_hint,
        preprocessor_hints=preprocessor_hints or None,
        today=today_str,
        lang=lang,
    )
    recent_messages = build_context_messages(context_messages)
    messages = build_messages(recent_messages, message, image_count=image_count)

    return AgentPromptInput(
        today=today_str,
        model=select_chat_model(
            is_emergency=is_emergency,
            default_model=default_model,
            emergency_model=emergency_model,
        ),
        emergency_hint=emergency_hint,
        preprocessor_hints=preprocessor_hints,
        retrieved_context=retrieved_context,
        memory_context=memory_context,
        system_prompt=system_prompt,
        messages=messages,
        recent_image_urls=recent_user_image_urls(context_messages),
    )
