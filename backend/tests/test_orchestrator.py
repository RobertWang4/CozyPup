import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.agents.orchestrator import run_orchestrator, OrchestratorResult


def _make_stream_chunks(content=None, tool_calls=None):
    """Create mock streaming chunks."""
    chunks = []

    if content:
        for char in content:
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta = MagicMock()
            chunk.choices[0].delta.content = char
            chunk.choices[0].delta.tool_calls = None
            chunks.append(chunk)

    if tool_calls:
        for i, tc in enumerate(tool_calls):
            # Name chunk
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta = MagicMock()
            chunk.choices[0].delta.content = None
            tc_delta = MagicMock()
            tc_delta.index = i
            tc_delta.id = f"call_{i}"
            tc_delta.function = MagicMock()
            tc_delta.function.name = tc["name"]
            tc_delta.function.arguments = json.dumps(tc["args"])
            chunk.choices[0].delta.tool_calls = [tc_delta]
            chunks.append(chunk)

    return chunks


class MockAsyncIterator:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
    def __aiter__(self):
        return self
    async def __anext__(self):
        try:
            return next(self.chunks)
        except StopIteration:
            raise StopAsyncIteration


@pytest.mark.asyncio
async def test_path_a_pure_chat():
    """No tools -> pure chat response."""
    chunks = _make_stream_chunks(content="你好！很高兴见到你")

    tokens = []
    async def capture_token(t):
        tokens.append(t)

    with patch("app.agents.orchestrator.litellm.acompletion", new_callable=AsyncMock, return_value=MockAsyncIterator(chunks)):
        result = await run_orchestrator(
            message="你好",
            system_prompt="test",
            context_messages=[{"role": "user", "content": "你好"}],
            on_token=capture_token,
        )

    assert result.response_text == "你好！很高兴见到你"
    assert len(result.cards) == 0
    assert len(tokens) > 0

@pytest.mark.asyncio
async def test_single_tool_call():
    """Single tool call -> execute and follow up."""
    tool_args = {"pet_id": "abc", "event_date": "2026-03-24", "title": "吃狗粮", "category": "diet"}
    chunks = _make_stream_chunks(tool_calls=[{"name": "create_calendar_event", "args": tool_args}])
    followup_chunks = _make_stream_chunks(content="已记录")

    call_count = 0
    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockAsyncIterator(chunks)
        return MockAsyncIterator(followup_chunks)

    mock_execute = AsyncMock(return_value={"success": True, "card": {"type": "record"}})
    mock_db = AsyncMock()

    cards = []
    async def capture_card(c):
        cards.append(c)

    with patch("app.agents.orchestrator.litellm.acompletion", new_callable=AsyncMock, side_effect=mock_completion), \
         patch("app.agents.orchestrator.validate_tool_args", return_value=[]), \
         patch("app.agents.orchestrator.execute_tool", mock_execute):
        result = await run_orchestrator(
            message="三妹吃了狗粮",
            system_prompt="test",
            context_messages=[{"role": "user", "content": "三妹吃了狗粮"}],
            db=mock_db, user_id="user-1",
            on_card=capture_card,
        )

    assert len(result.cards) == 1
    assert result.cards[0]["type"] == "record"


@pytest.mark.asyncio
async def test_multi_tool_calls():
    """Multiple tool calls in one round -> all executed sequentially."""
    tool_args_1 = {"pet_id": "abc", "event_date": "2026-03-24", "title": "吃狗粮", "category": "diet"}
    tool_args_2 = {"pet_id": "def", "event_date": "2026-03-24", "title": "打疫苗", "category": "medical"}

    chunks = _make_stream_chunks(
        content="好的，",
        tool_calls=[
            {"name": "create_calendar_event", "args": tool_args_1},
            {"name": "create_calendar_event", "args": tool_args_2},
        ]
    )
    followup_chunks = _make_stream_chunks(content="都记录好了")

    call_count = 0
    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockAsyncIterator(chunks)
        return MockAsyncIterator(followup_chunks)

    mock_execute = AsyncMock(return_value={"success": True, "card": {"type": "record"}})
    mock_db = AsyncMock()

    cards = []
    async def capture_card(c):
        cards.append(c)

    with patch("app.agents.orchestrator.litellm.acompletion", new_callable=AsyncMock, side_effect=mock_completion), \
         patch("app.agents.orchestrator.validate_tool_args", return_value=[]), \
         patch("app.agents.orchestrator.execute_tool", mock_execute):
        result = await run_orchestrator(
            message="三妹吃了狗粮，豆豆打了疫苗",
            system_prompt="test",
            context_messages=[{"role": "user", "content": "三妹吃了狗粮，豆豆打了疫苗"}],
            db=mock_db, user_id="user-1",
            on_card=capture_card,
        )

    assert len(result.cards) == 2
    assert mock_execute.call_count == 2


@pytest.mark.asyncio
async def test_confirm_gate_single():
    """Single delete task -> confirm card."""
    chunks = _make_stream_chunks(tool_calls=[{"name": "delete_pet", "args": {"pet_id": "abc"}}])

    cards = []
    async def capture_card(c):
        cards.append(c)

    with patch("app.agents.orchestrator.litellm.acompletion", new_callable=AsyncMock, return_value=MockAsyncIterator(chunks)), \
         patch("app.agents.orchestrator.validate_tool_args", return_value=[]), \
         patch("app.agents.orchestrator.store_action", new_callable=AsyncMock, return_value="action-123"):
        result = await run_orchestrator(
            message="删除三妹",
            system_prompt="test",
            context_messages=[{"role": "user", "content": "删除三妹"}],
            db=AsyncMock(), user_id="user-1", session_id="session-1",
            on_card=capture_card,
        )

    assert len(result.confirm_cards) == 1
    assert result.confirm_cards[0]["type"] == "confirm_action"

@pytest.mark.asyncio
async def test_error_handling():
    """LLM error -> graceful fallback."""
    with patch("app.agents.orchestrator.litellm.acompletion", new_callable=AsyncMock, side_effect=Exception("API error")):
        tokens = []
        result = await run_orchestrator(
            message="test",
            system_prompt="test",
            context_messages=[{"role": "user", "content": "test"}],
            on_token=lambda t: tokens.append(t),
        )

    assert "抱歉" in result.response_text or "错误" in result.response_text


@pytest.mark.asyncio
async def test_nudge_triggers_when_tools_missed():
    """When pre-processor expects a NUDGE_TOOLS tool but LLM doesn't call any, nudge fires.

    Nudge only fires for tools in NUDGE_TOOLS (search_places, trigger_emergency,
    set_language). Using search_places here to exercise the nudge path.
    """
    from app.agents.pre_processing.types import SuggestedAction

    # Round 1: LLM returns text only (no tools)
    round1_chunks = _make_stream_chunks(content="附近有宠物医院哦")

    # Round 2 (after nudge): LLM calls the tool
    search_args = {"query": "宠物医院", "location": "current"}
    round2_chunks = _make_stream_chunks(tool_calls=[{"name": "search_places", "args": search_args}])

    # Round 3: follow-up text
    round3_chunks = _make_stream_chunks(content="找到了几家医院")

    call_count = 0
    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockAsyncIterator(round1_chunks)
        elif call_count == 2:
            return MockAsyncIterator(round2_chunks)
        return MockAsyncIterator(round3_chunks)

    mock_execute = AsyncMock(return_value={"success": True, "card": {"type": "places"}})
    mock_db = AsyncMock()

    suggested = [SuggestedAction(
        tool_name="search_places",
        arguments=search_args,
        confidence=0.9,
    )]

    with patch("app.agents.orchestrator.litellm.acompletion", new_callable=AsyncMock, side_effect=mock_completion), \
         patch("app.agents.orchestrator.validate_tool_args", return_value=[]), \
         patch("app.agents.orchestrator.execute_tool", mock_execute):
        result = await run_orchestrator(
            message="附近哪里有宠物医院",
            system_prompt="test",
            context_messages=[{"role": "user", "content": "附近哪里有宠物医院"}],
            db=mock_db, user_id="user-1",
            suggested_actions=suggested,
        )

    # Nudge should have triggered: 3 LLM calls (initial + nudge + follow-up)
    assert call_count == 3
    assert len(result.cards) == 1
    assert "search_places" in result.tools_called
