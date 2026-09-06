"""Reusable agent engine adapter.

Holds the compiled LangGraph agent graph (`agents/graph.py`). The HTTP route
consumes `astream` and forwards the graph's custom stream straight to SSE;
`run` is the callback-based variant kept for the CLI harness and evals.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from app.agents.checkpointer import get_checkpointer
from app.agents.constants import maybe_await
from app.agents.graph import get_graph, stream_agent
from app.agents.orchestrator import run_orchestrator
from app.agents.runtime import AgentEvent, AgentRunResult


@dataclass
class AgentRunInput:
    message: str
    messages: list[dict] = field(default_factory=list)
    system_prompt: str = ""
    location: dict | None = None
    language: str = "zh"
    image_urls: list[str] = field(default_factory=list)
    model: str | None = None
    db: object | None = None
    user_id: object | None = None
    session_id: object | None = None


class AgentEngine:
    def __init__(self, checkpointer=None):
        # No checkpointer configured (tests, harness, or a failed Postgres
        # setup) → `get_graph` falls back to an in-process saver so the graph
        # still runs; only cross-request resume is unavailable.
        self.graph = get_graph(checkpointer or get_checkpointer())

    async def astream(
        self,
        run_input: AgentRunInput,
        **kwargs,
    ) -> AsyncIterator[tuple[str, Any]]:
        """Stream one run: ("sse", {event, data}) items, then ("result", res)."""
        async for item in stream_agent(
            graph=self.graph,
            system_prompt=run_input.system_prompt,
            context_messages=run_input.messages or [
                {"role": "user", "content": run_input.message}
            ],
            model=run_input.model,
            db=run_input.db,
            user_id=run_input.user_id,
            session_id=run_input.session_id,
            lang=run_input.language,
            location=run_input.location,
            image_urls=run_input.image_urls,
            **kwargs,
        ):
            yield item

    async def run(
        self,
        run_input: AgentRunInput,
        *,
        on_token: Callable[[str], Awaitable[None]] | None = None,
        on_card: Callable[[dict], Awaitable[None]] | None = None,
        on_event: Callable[[AgentEvent], Awaitable[None]] | None = None,
        **kwargs,
    ) -> AgentRunResult:
        started = time.perf_counter()
        context_messages = run_input.messages or [
            {"role": "user", "content": run_input.message}
        ]

        async def emit(event: AgentEvent) -> None:
            if on_event:
                await maybe_await(on_event, event)

        async def handle_token(text: str) -> None:
            await emit(AgentEvent(type="token", data={"text": text}))
            if on_token:
                await maybe_await(on_token, text)

        async def handle_card(card: dict) -> None:
            await emit(AgentEvent(type="card", data={"card": card}))
            if on_card:
                await maybe_await(on_card, card)

        await emit(AgentEvent(type="run_started", data={"message": run_input.message}))
        try:
            result = await run_orchestrator(
                message=run_input.message,
                system_prompt=run_input.system_prompt,
                context_messages=context_messages,
                model=run_input.model,
                db=run_input.db,
                user_id=run_input.user_id,
                session_id=run_input.session_id,
                on_token=handle_token,
                on_card=handle_card,
                lang=run_input.language,
                location=run_input.location,
                image_urls=run_input.image_urls,
                **kwargs,
            )
        except Exception as exc:
            await emit(AgentEvent(type="run_error", data={"error": str(exc)[:200]}))
            raise

        run_result = AgentRunResult.success(
            response_text=result.response_text,
            cards=result.cards,
            confirm_cards=result.confirm_cards,
            tools_called=sorted(result.tools_called),
            tools_executed=sorted(result.tools_executed),
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            prompt_tokens=result.total_prompt_tokens,
            completion_tokens=result.total_completion_tokens,
            model_used=result.model_used,
        )
        await emit(AgentEvent(type="run_finished", data={"status": run_result.status}))
        return run_result
