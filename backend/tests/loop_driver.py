"""Callback-style driver over `graph.stream_agent`, for tests only.

Production drives the graph through `AgentEngine.astream` and consumes the
raw ("sse", ...) / ("result", ...) stream. These tests predate that and are
written against on_token / on_card callbacks, so this adapter translates the
stream back into callbacks. It lives in tests/ on purpose — shipping it in
`app/` would be a second, unused entry point into the loop.
"""

from typing import Awaitable, Callable

from app.agents.constants import maybe_await
from app.agents.loop import OrchestratorResult
from app.agents.pre_processing.types import SuggestedAction
from app.agents.trace_collector import INACTIVE_TRACE, TraceCollector


async def run_loop(
    message: str,
    system_prompt: str,
    context_messages: list[dict],
    model: str | None = None,
    db=None,
    user_id=None,
    session_id=None,
    on_token: Callable[[str], Awaitable[None]] | None = None,
    on_card: Callable[[dict], Awaitable[None]] | None = None,
    on_thinking: Callable[[str, str], Awaitable[None]] | None = None,
    today: str = "",
    suggested_actions: list[SuggestedAction] | None = None,
    trace: TraceCollector = INACTIVE_TRACE,
    **kwargs,
) -> OrchestratorResult:
    from app.agents.graph import stream_agent

    lang = kwargs.pop("lang", "zh")
    result = OrchestratorResult()

    async for kind, payload in stream_agent(
        system_prompt=system_prompt,
        context_messages=context_messages,
        model=model,
        db=db,
        user_id=user_id,
        session_id=session_id,
        lang=lang,
        today=today,
        suggested_actions=suggested_actions,
        trace=trace,
        images=kwargs.pop("images", None),
        image_urls=kwargs.pop("image_urls", None),
        recent_image_urls=kwargs.pop("recent_image_urls", None),
        location=kwargs.pop("location", None),
        pets=kwargs.pop("pets", None),
    ):
        if kind == "result":
            result = payload
            continue
        event, data = payload["event"], payload["data"]
        if event == "token" and on_token:
            await maybe_await(on_token, data["text"])
        elif event == "thinking" and on_thinking:
            await maybe_await(on_thinking, data["text"], data["tool"])
        elif event == "card" and on_card:
            await maybe_await(on_card, data)

    return result
