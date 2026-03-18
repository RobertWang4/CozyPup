import logging
import pytest

from app.agents.base import BaseAgent
from app.debug.correlation import get_pet_id
from app.debug.error_types import AgentError


class EchoAgent(BaseAgent):
    name = "echo_agent"

    async def _run(self, message: str, context: dict, **kwargs) -> dict:
        return {"result": "ok"}


class FailingAgent(BaseAgent):
    name = "failing_agent"

    async def _run(self, message: str, context: dict, **kwargs) -> dict:
        raise AgentError("test error")


@pytest.mark.asyncio
async def test_execute_logs_agent_start(caplog):
    agent = EchoAgent()
    with caplog.at_level(logging.DEBUG, logger="app.agents.echo_agent"):
        await agent.execute("hello", {})
    assert any("agent_start" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_execute_logs_agent_complete_with_duration(caplog):
    agent = EchoAgent()
    with caplog.at_level(logging.INFO, logger="app.agents.echo_agent"):
        await agent.execute("hello", {})
    complete_records = [r for r in caplog.records if r.message == "agent_complete"]
    assert len(complete_records) == 1
    assert hasattr(complete_records[0], "duration_ms")
    assert isinstance(complete_records[0].duration_ms, int)


@pytest.mark.asyncio
async def test_execute_logs_agent_error_and_reraises(caplog):
    agent = FailingAgent()
    with caplog.at_level(logging.ERROR, logger="app.agents.failing_agent"):
        with pytest.raises(AgentError, match="test error"):
            await agent.execute("hello", {})
    error_records = [r for r in caplog.records if r.message == "agent_error"]
    assert len(error_records) == 1
    assert error_records[0].error_type == "AgentError"


@pytest.mark.asyncio
async def test_pet_id_set_in_contextvar():
    agent = EchoAgent()
    await agent.execute("hello", {"pet_id": "pet-123"})
    # pet_id is reset after execute completes (no leakage)
    assert get_pet_id() == ""


@pytest.mark.asyncio
async def test_execute_returns_run_result():
    agent = EchoAgent()
    result = await agent.execute("hello", {})
    assert result == {"result": "ok"}


def test_subclass_without_name_raises():
    with pytest.raises(TypeError, match=r"must define a class-level .name"):
        class UnnamedAgent(BaseAgent):
            async def _run(self, message, context, **kwargs):
                return {}
