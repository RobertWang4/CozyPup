import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.agents.executor import run_executor, ExecutorResult, CONFIRM_TOOLS


def _make_llm_response(tool_name=None, tool_args=None, content=None):
    """Helper to create mock LLM response."""
    msg = MagicMock()
    msg.content = content
    if tool_name:
        tc = MagicMock()
        tc.id = "call_123"
        tc.function.name = tool_name
        tc.function.arguments = json.dumps(tool_args or {})
        msg.tool_calls = [tc]
    else:
        msg.tool_calls = None

    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message = msg
    return response


@pytest.mark.asyncio
async def test_executor_no_tool_needed():
    """LLM decides no tool is needed."""
    response = _make_llm_response(content="这个问题不需要工具")
    with patch("app.agents.executor.litellm.acompletion", new_callable=AsyncMock, return_value=response):
        result = await run_executor("回答用户问题", "用户问好")
    assert result.success is True
    assert result.tool is None


@pytest.mark.asyncio
async def test_executor_calls_tool():
    """LLM calls a tool successfully."""
    args = {"pet_id": "abc-123", "event_date": "2026-03-24", "title": "吃狗粮", "category": "diet"}
    response = _make_llm_response("create_calendar_event", args)

    mock_execute = AsyncMock(return_value={"success": True, "card": {"type": "record"}})
    mock_db = AsyncMock()

    with patch("app.agents.executor.litellm.acompletion", new_callable=AsyncMock, return_value=response), \
         patch("app.agents.executor.validate_tool_args", return_value=[]), \
         patch("app.agents.executor.execute_tool", mock_execute):
        result = await run_executor(
            "记录三妹吃狗粮", "三妹(id=abc-123)",
            db=mock_db, user_id="user-1", today="2026-03-24"
        )

    assert result.success is True
    assert result.tool == "create_calendar_event"
    assert result.card is not None


@pytest.mark.asyncio
async def test_executor_confirm_gate():
    """Destructive tools return needs_confirm."""
    for tool_name in CONFIRM_TOOLS:
        args = {"pet_id": "abc-123"}
        response = _make_llm_response(tool_name, args)

        with patch("app.agents.executor.litellm.acompletion", new_callable=AsyncMock, return_value=response), \
             patch("app.agents.executor.validate_tool_args", return_value=[]):
            result = await run_executor(f"执行{tool_name}", "context")

        assert result.needs_confirm is True
        assert result.tool == tool_name


@pytest.mark.asyncio
async def test_executor_validation_retry():
    """Validation error triggers one retry."""
    bad_args = {"pet_id": "not-a-uuid"}
    good_args = {"pet_id": "abc-123", "event_date": "2026-03-24", "title": "test", "category": "diet"}

    first_response = _make_llm_response("create_calendar_event", bad_args)
    retry_response = _make_llm_response("create_calendar_event", good_args)

    call_count = 0
    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        return first_response if call_count == 1 else retry_response

    mock_execute = AsyncMock(return_value={"success": True})
    mock_db = AsyncMock()

    with patch("app.agents.executor.litellm.acompletion", new_callable=AsyncMock, side_effect=mock_completion), \
         patch("app.agents.executor.validate_tool_args", side_effect=[["invalid uuid"], []]), \
         patch("app.agents.executor.execute_tool", mock_execute):
        result = await run_executor(
            "记录事件", "context",
            db=mock_db, user_id="user-1"
        )

    assert call_count == 2  # original + retry
    assert result.success is True


@pytest.mark.asyncio
async def test_executor_handles_error():
    """Executor handles LLM errors gracefully."""
    with patch("app.agents.executor.litellm.acompletion", new_callable=AsyncMock, side_effect=Exception("API down")):
        result = await run_executor("do something", "context")
    assert result.success is False
    assert "API down" in result.error


@pytest.mark.asyncio
async def test_executor_no_db_returns_error():
    """Executor returns error when db/user_id not provided for non-confirm tool."""
    args = {"pet_id": "abc-123", "event_date": "2026-03-24", "title": "test", "category": "diet"}
    response = _make_llm_response("create_calendar_event", args)

    with patch("app.agents.executor.litellm.acompletion", new_callable=AsyncMock, return_value=response), \
         patch("app.agents.executor.validate_tool_args", return_value=[]):
        result = await run_executor("记录事件", "context")

    assert result.success is False
    assert "No database session" in result.error


@pytest.mark.asyncio
async def test_executor_filtered_tools():
    """available_tools filters which tools are passed to LLM."""
    response = _make_llm_response(content="no tool needed")

    with patch("app.agents.executor.litellm.acompletion", new_callable=AsyncMock, return_value=response) as mock_llm:
        await run_executor("test", "context", available_tools=["create_pet"])

    # Check that filtered tools were passed
    call_kwargs = mock_llm.call_args[1]
    tool_names = [t["function"]["name"] for t in call_kwargs["tools"]]
    assert "create_pet" in tool_names
    assert len(tool_names) == 1


@pytest.mark.asyncio
async def test_executor_no_matching_tools():
    """Returns error when no tools match available_tools filter."""
    result = await run_executor("test", "context", available_tools=["nonexistent_tool"])
    assert result.success is False
    assert "No matching tools" in result.error
