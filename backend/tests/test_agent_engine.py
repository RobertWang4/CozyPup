import pytest
from pathlib import Path

from app.agents.runtime import RunStatus


@pytest.mark.asyncio
async def test_agent_engine_returns_run_result(monkeypatch):
    async def fake_run_orchestrator(**kwargs):
        from app.agents.orchestrator import OrchestratorResult

        return OrchestratorResult(
            response_text="ok",
            model_used="test-model",
            total_prompt_tokens=10,
            total_completion_tokens=5,
        )

    monkeypatch.setattr("app.agents.engine.run_orchestrator", fake_run_orchestrator)

    from app.agents.engine import AgentEngine, AgentRunInput

    engine = AgentEngine()
    result = await engine.run(AgentRunInput(message="hello"))

    assert result.ok is True
    assert result.response_text == "ok"
    assert result.model_used == "test-model"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5


@pytest.mark.asyncio
async def test_agent_engine_emits_token_card_and_result_events(monkeypatch):
    async def fake_run_orchestrator(**kwargs):
        from app.agents.orchestrator import OrchestratorResult

        await kwargs["on_token"]("hello")
        await kwargs["on_card"]({"type": "record"})
        return OrchestratorResult(response_text="hello", model_used="test-model")

    monkeypatch.setattr("app.agents.engine.run_orchestrator", fake_run_orchestrator)

    from app.agents.engine import AgentEngine, AgentRunInput

    events = []

    async def on_event(event):
        events.append(event)

    result = await AgentEngine().run(
        AgentRunInput(message="hello"),
        on_event=on_event,
    )

    assert [event.type for event in events] == [
        "run_started",
        "token",
        "card",
        "run_finished",
    ]
    assert events[1].data == {"text": "hello"}
    assert events[2].data == {"card": {"type": "record"}}
    assert result.status == RunStatus.SUCCESS


@pytest.mark.asyncio
async def test_agent_engine_forwards_production_kwargs(monkeypatch):
    seen = {}

    async def fake_run_orchestrator(**kwargs):
        seen.update(kwargs)
        from app.agents.orchestrator import OrchestratorResult

        return OrchestratorResult(response_text="ok")

    monkeypatch.setattr("app.agents.engine.run_orchestrator", fake_run_orchestrator)

    from app.agents.engine import AgentEngine, AgentRunInput

    async def on_thinking(text, tool):
        pass

    await AgentEngine().run(
        AgentRunInput(message="hello", system_prompt="sys"),
        on_thinking=on_thinking,
        today="2026-06-12",
        suggested_actions=["suggestion"],
        images=["base64"],
        recent_image_urls=["/photo.jpg"],
        pets=["Max"],
        trace="trace",
    )

    assert seen["on_thinking"] is on_thinking
    assert seen["today"] == "2026-06-12"
    assert seen["suggested_actions"] == ["suggestion"]
    assert seen["images"] == ["base64"]
    assert seen["recent_image_urls"] == ["/photo.jpg"]
    assert seen["pets"] == ["Max"]
    assert seen["trace"] == "trace"


def test_chat_route_uses_agent_engine_entrypoint():
    source = Path("app/routers/chat.py").read_text()

    assert "from app.agents.engine import AgentEngine, AgentRunInput" in source
    assert "AgentEngine().astream(" in source
    assert "await run_orchestrator(" not in source


@pytest.mark.asyncio
async def test_agent_engine_preserves_confirm_cards(monkeypatch):
    async def fake_run_orchestrator(**kwargs):
        from app.agents.orchestrator import OrchestratorResult

        return OrchestratorResult(
            response_text="confirm first",
            confirm_cards=[{"type": "confirm_action", "action_id": "a1"}],
        )

    monkeypatch.setattr("app.agents.engine.run_orchestrator", fake_run_orchestrator)

    from app.agents.engine import AgentEngine, AgentRunInput

    result = await AgentEngine().run(AgentRunInput(message="delete it"))

    assert result.confirm_cards == [{"type": "confirm_action", "action_id": "a1"}]
