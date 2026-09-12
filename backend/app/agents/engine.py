"""Reusable agent engine adapter.

Holds the compiled LangGraph agent graph (`agents/graph.py`). The HTTP route
consumes `astream` and forwards the graph's custom stream straight to SSE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.agents.checkpointer import get_checkpointer
from app.agents.graph import get_graph, stream_agent


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
