from pathlib import Path


def test_chat_route_uses_agent_engine_entrypoint():
    source = Path("app/routers/chat.py").read_text()

    assert "from app.agents.engine import AgentEngine, AgentRunInput" in source
    assert "AgentEngine().astream(" in source
    assert "await run_orchestrator(" not in source


def test_agent_engine_has_no_callback_entrypoint():
    """`AgentEngine.run` / `run_orchestrator` were the pre-LangGraph path.

    Production streams the graph directly; re-adding a second entry point
    means two loops to keep in sync. Tests drive it via tests/loop_driver.py.
    """
    from app.agents.engine import AgentEngine

    assert not hasattr(AgentEngine, "run")
    assert "run_orchestrator" not in Path("app/agents/loop.py").read_text()
