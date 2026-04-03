"""
Agent V2 Integration Tests
Tests the full pipeline: preprocessing -> orchestrator -> response
All LLM calls are mocked, but the pipeline logic is real.
"""
import json
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.emergency import EmergencyCheckResult, build_emergency_hint, detect_emergency
from app.agents.orchestrator import OrchestratorResult, run_orchestrator
from app.agents.locale import t
from app.agents.pre_processing import (
    SuggestedAction,
    pre_process,
)
from app.agents.prompts_v2 import build_system_prompt
from app.agents.tools import TOOL_DEFINITIONS
from app.agents.context_agent import should_summarize, summarize_context


# ========== Helpers ==========

def _make_stream_chunks(content=None, tool_calls=None):
    """Create mock streaming chunks for litellm.acompletion."""
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


def _make_pet(name, pet_id=None, species="dog"):
    return SimpleNamespace(
        id=pet_id or str(uuid.uuid4()),
        name=name,
        species=SimpleNamespace(value=species),
        breed=None,
        weight=None,
        birthday=None,
        profile_md=None,
        profile=None,
    )


# ============================================
# Test 1: Pure Chat Path
# ============================================
@pytest.mark.asyncio
async def test_pure_chat_no_tools():
    """Send a greeting -> orchestrator responds without calling any tools."""
    chunks = _make_stream_chunks(content="你好呀！有什么可以帮你的吗？")

    tokens = []

    async def capture_token(t):
        tokens.append(t)

    cards = []

    async def capture_card(c):
        cards.append(c)

    with patch(
        "app.agents.orchestrator.litellm.acompletion",
        new_callable=AsyncMock,
        return_value=MockAsyncIterator(chunks),
    ):
        result = await run_orchestrator(
            message="你好",
            system_prompt="test prompt",
            context_messages=[{"role": "user", "content": "你好"}],
            on_token=capture_token,
            on_card=capture_card,
        )

    assert result.response_text == "你好呀！有什么可以帮你的吗？"
    assert len(result.cards) == 0
    assert len(result.confirm_cards) == 0
    assert len(cards) == 0
    assert len(tokens) > 0


# ============================================
# Test 2: Single Task — Tool Call
# ============================================
@pytest.mark.asyncio
async def test_single_task_creates_event():
    """Send '三妹吃了狗粮' -> orchestrator calls create_calendar_event -> card returned."""
    tool_args = {
        "pet_id": "abc-123",
        "event_date": "2026-03-24",
        "title": "吃狗粮",
        "category": "diet",
    }
    initial_chunks = _make_stream_chunks(
        tool_calls=[{"name": "create_calendar_event", "args": tool_args}]
    )
    followup_chunks = _make_stream_chunks(content="已帮你记录三妹吃了狗粮")

    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockAsyncIterator(initial_chunks)
        return MockAsyncIterator(followup_chunks)

    mock_execute = AsyncMock(
        return_value={"success": True, "card": {"type": "record", "category": "diet"}}
    )
    mock_db = AsyncMock()

    cards = []

    async def capture_card(c):
        cards.append(c)

    tokens = []

    async def capture_token(t):
        tokens.append(t)

    with patch(
        "app.agents.orchestrator.litellm.acompletion",
        new_callable=AsyncMock,
        side_effect=mock_completion,
    ), patch("app.agents.orchestrator.validate_tool_args", return_value=[]), patch(
        "app.agents.orchestrator.execute_tool", mock_execute
    ):
        result = await run_orchestrator(
            message="三妹吃了狗粮",
            system_prompt="test",
            context_messages=[{"role": "user", "content": "三妹吃了狗粮"}],
            db=mock_db,
            user_id="user-1",
            on_token=capture_token,
            on_card=capture_card,
        )

    assert len(result.cards) == 1
    assert result.cards[0]["type"] == "record"
    assert len(cards) == 1
    mock_execute.assert_called_once()
    mock_db.commit.assert_called_once()
    assert "三妹" in result.response_text or "记录" in result.response_text


# ============================================
# Test 3: Multi Tool Calls — Sequential in Unified Loop
# ============================================
@pytest.mark.asyncio
async def test_multi_tool_sequential_execution():
    """Send '三妹吃了狗粮，豆豆打了疫苗' -> 2 tool calls in one round -> 2 cards."""
    tool_args_1 = {
        "pet_id": "abc",
        "event_date": "2026-03-24",
        "title": "吃狗粮",
        "category": "diet",
    }
    tool_args_2 = {
        "pet_id": "def",
        "event_date": "2026-03-24",
        "title": "打疫苗",
        "category": "medical",
    }
    chunks = _make_stream_chunks(
        content="好的，",
        tool_calls=[
            {"name": "create_calendar_event", "args": tool_args_1},
            {"name": "create_calendar_event", "args": tool_args_2},
        ],
    )
    followup_chunks = _make_stream_chunks(content="都记录好了")

    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockAsyncIterator(chunks)
        return MockAsyncIterator(followup_chunks)

    mock_execute = AsyncMock(
        return_value={"success": True, "card": {"type": "record"}}
    )
    mock_db = AsyncMock()

    cards = []

    async def capture_card(c):
        cards.append(c)

    with patch(
        "app.agents.orchestrator.litellm.acompletion",
        new_callable=AsyncMock,
        side_effect=mock_completion,
    ), patch("app.agents.orchestrator.validate_tool_args", return_value=[]), patch(
        "app.agents.orchestrator.execute_tool", mock_execute
    ):
        result = await run_orchestrator(
            message="三妹吃了狗粮，豆豆打了疫苗",
            system_prompt="test",
            context_messages=[
                {"role": "user", "content": "三妹吃了狗粮，豆豆打了疫苗"}
            ],
            db=mock_db,
            user_id="user-1",
            on_card=capture_card,
        )

    assert len(result.cards) == 2
    assert len(cards) == 2
    assert mock_execute.call_count == 2


# ============================================
# Test 4: Emergency Detection -> trigger_emergency
# ============================================
@pytest.mark.asyncio
async def test_emergency_triggers_tool():
    """Send '我家猫中毒了' -> emergency keywords detected -> LLM calls trigger_emergency."""
    # Step 1: verify detection
    check = detect_emergency("我家猫中毒了")
    assert check.detected is True
    assert "中毒" in check.keywords

    # Step 2: verify hint
    hint = build_emergency_hint(check.keywords)
    assert "trigger_emergency" in hint

    # Step 3: full pipeline
    emergency_args = {
        "symptoms": "中毒",
        "first_aid": "催吐并立即送医",
        "severity": "critical",
    }
    initial_chunks = _make_stream_chunks(
        tool_calls=[{"name": "trigger_emergency", "args": emergency_args}]
    )
    followup_chunks = _make_stream_chunks(content="请立即带猫去最近的宠物医院！")

    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockAsyncIterator(initial_chunks)
        return MockAsyncIterator(followup_chunks)

    mock_execute = AsyncMock(
        return_value={
            "success": True,
            "card": {"type": "emergency", "symptoms": "中毒"},
        }
    )
    mock_db = AsyncMock()

    cards = []

    async def capture_card(c):
        cards.append(c)

    system_prompt = build_system_prompt(
        pets=[],
        emergency_hint=hint,
        today="2026-03-24",
    )

    with patch(
        "app.agents.orchestrator.litellm.acompletion",
        new_callable=AsyncMock,
        side_effect=mock_completion,
    ), patch("app.agents.orchestrator.validate_tool_args", return_value=[]), patch(
        "app.agents.orchestrator.execute_tool", mock_execute
    ):
        result = await run_orchestrator(
            message="我家猫中毒了",
            system_prompt=system_prompt,
            context_messages=[{"role": "user", "content": "我家猫中毒了"}],
            db=mock_db,
            user_id="user-1",
            on_card=capture_card,
        )

    assert len(result.cards) == 1
    assert result.cards[0]["type"] == "emergency"


# ============================================
# Test 5: Emergency False Positive Prevention
# ============================================
@pytest.mark.asyncio
async def test_emergency_false_positive_blocked():
    """Send '上次中毒是什么时候' -> keywords detected but LLM does NOT trigger emergency."""
    check = detect_emergency("上次中毒是什么时候")
    assert check.detected is True

    query_args = {"pet_id": "abc", "category": "abnormal"}
    initial_chunks = _make_stream_chunks(
        tool_calls=[{"name": "query_calendar_events", "args": query_args}]
    )
    followup_chunks = _make_stream_chunks(content="上次中毒记录是3月10日")

    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockAsyncIterator(initial_chunks)
        return MockAsyncIterator(followup_chunks)

    mock_execute = AsyncMock(
        return_value={
            "success": True,
            "events": [{"date": "2026-03-10", "category": "abnormal"}],
        }
    )
    mock_db = AsyncMock()

    cards = []

    async def capture_card(c):
        cards.append(c)

    hint = build_emergency_hint(check.keywords)
    system_prompt = build_system_prompt(emergency_hint=hint, today="2026-03-24")

    with patch(
        "app.agents.orchestrator.litellm.acompletion",
        new_callable=AsyncMock,
        side_effect=mock_completion,
    ), patch("app.agents.orchestrator.validate_tool_args", return_value=[]), patch(
        "app.agents.orchestrator.execute_tool", mock_execute
    ):
        result = await run_orchestrator(
            message="上次中毒是什么时候",
            system_prompt=system_prompt,
            context_messages=[{"role": "user", "content": "上次中毒是什么时候"}],
            db=mock_db,
            user_id="user-1",
            on_card=capture_card,
        )

    emergency_cards = [c for c in cards if c.get("type") == "emergency"]
    assert len(emergency_cards) == 0
    mock_execute.assert_called_once()


# ============================================
# Test 6: Confirm Flow for Destructive Operations
# ============================================
@pytest.mark.asyncio
async def test_confirm_flow_delete_pet():
    """Send '删除三妹' -> confirm card returned, NOT direct execution."""
    chunks = _make_stream_chunks(
        tool_calls=[{"name": "delete_pet", "args": {"pet_id": "abc-123"}}]
    )

    cards = []

    async def capture_card(c):
        cards.append(c)

    mock_db = AsyncMock()
    mock_execute = AsyncMock()

    with patch(
        "app.agents.orchestrator.litellm.acompletion",
        new_callable=AsyncMock,
        return_value=MockAsyncIterator(chunks),
    ), patch("app.agents.orchestrator.validate_tool_args", return_value=[]), patch(
        "app.agents.orchestrator.store_action", new_callable=AsyncMock, return_value="action-456"
    ), patch(
        "app.agents.orchestrator.execute_tool", mock_execute
    ):
        result = await run_orchestrator(
            message="删除三妹",
            system_prompt="test",
            context_messages=[{"role": "user", "content": "删除三妹"}],
            db=mock_db,
            user_id="user-1",
            session_id="session-1",
            on_card=capture_card,
        )

    assert len(result.confirm_cards) == 1
    assert result.confirm_cards[0]["type"] == "confirm_action"
    assert result.confirm_cards[0]["action_id"] == "action-456"
    mock_execute.assert_not_called()


# ============================================
# Test 7: Context Compression Trigger
# ============================================
def test_context_compression_triggered():
    """After 5+ messages, context_agent summary should be triggered."""
    assert should_summarize(total_messages=6, summarized_up_to=0) is True
    assert should_summarize(total_messages=4, summarized_up_to=0) is False
    assert should_summarize(total_messages=10, summarized_up_to=5) is True
    assert should_summarize(total_messages=10, summarized_up_to=6) is False
    assert should_summarize(total_messages=5, summarized_up_to=None) is True
    assert should_summarize(total_messages=4, summarized_up_to=None) is False


@pytest.mark.asyncio
async def test_context_summarize_returns_structured():
    """summarize_context returns structured summary with expected keys."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(
        {
            "topics": ["喂食", "疫苗"],
            "pending": "下周打疫苗",
            "mood": "开心",
            "key_facts": ["三妹吃了200克狗粮", "豆豆需要打疫苗"],
        }
    )

    with patch(
        "app.agents.context_agent.litellm.acompletion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        summary = await summarize_context(
            messages=[
                {"role": "user", "content": "三妹吃了200克狗粮"},
                {"role": "assistant", "content": "已记录"},
            ]
        )

    assert "topics" in summary
    assert "key_facts" in summary
    assert len(summary["topics"]) == 2
    assert summary["mood"] == "开心"


# ============================================
# Test 8: Prompt Structure (Cache-Friendly)
# ============================================
def test_prompt_cache_friendly_order():
    """Verify prompt has static content first, dynamic content last."""
    prompt = build_system_prompt(
        pets=[],
        session_summary={"topics": ["喂食"], "key_facts": ["三妹吃了狗粮"]},
        emergency_hint="⚠️ 检测到紧急关键词",
        preprocessor_hints=["create_calendar_event(...)"],
        today="2026-03-24",
    )

    assert "工具选择" in prompt

    tree_pos = prompt.find("工具选择")
    summary_pos = prompt.find("对话摘要")
    hint_pos = prompt.find("⚠️")
    preprocessor_pos = prompt.find("系统检测到")

    assert tree_pos < summary_pos, "Tool guide should come before session summary"
    assert summary_pos < hint_pos, "Summary should come before emergency hint"
    assert hint_pos < preprocessor_pos, "Emergency hint should come before preprocessor hints"


def test_prompt_includes_pet_context():
    """Prompt includes pet profiles when provided."""
    pet = _make_pet("三妹", pet_id="abc-123")
    prompt = build_system_prompt(pets=[pet], today="2026-03-24")
    assert "三妹" in prompt
    assert "abc-123" in prompt


def test_prompt_without_pets():
    """Prompt handles no pets gracefully."""
    prompt = build_system_prompt(pets=[], today="2026-03-24")
    assert "还没有添加宠物" in prompt


# ============================================
# Test 9: Tool Decision Tree Exists
# ============================================
def test_tool_decision_tree_loaded():
    """Verify locale has the decision tree with all key tools."""
    tree = t("tool_decision_tree", "zh")
    assert "create_calendar_event" in tree
    assert "query_calendar_events" in tree
    assert "trigger_emergency" in tree
    assert "create_reminder" in tree
    assert "update_pet_profile" in tree


# ============================================
# Test 10: Enhanced Tool Descriptions
# ============================================
def test_tool_descriptions_enhanced():
    """Verify all tools have meaningful descriptions (not just one line)."""
    for tool in TOOL_DEFINITIONS:
        desc = tool["function"]["description"]
        name = tool["function"]["name"]
        assert len(desc) > 30, f"Tool {name} description too short: {desc}"


def test_tool_definitions_have_required_fields():
    """All tool definitions have correct structure."""
    for tool in TOOL_DEFINITIONS:
        assert tool["type"] == "function"
        assert "name" in tool["function"]
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]
        params = tool["function"]["parameters"]
        assert params["type"] == "object"
        assert "properties" in params


# ============================================
# Test 11: Pre-processor Hint Format
# ============================================
def test_preprocessor_hint_format():
    """Verify pre-processor outputs executable hints for high-confidence actions."""
    pet = _make_pet("三妹", pet_id=str(uuid.uuid4()))
    actions = pre_process("三妹吃了狗粮", [pet], today=date(2026, 3, 24))

    assert len(actions) >= 1
    assert actions[0].tool_name == "create_calendar_event"
    assert actions[0].confidence >= 0.8
    assert actions[0].arguments["category"] == "diet"


def test_preprocessor_question_no_action():
    """Questions should not produce calendar event actions."""
    pet = _make_pet("三妹", pet_id=str(uuid.uuid4()))
    actions = pre_process("三妹上次吃了什么？", [pet], today=date(2026, 3, 24))

    create_actions = [a for a in actions if a.tool_name == "create_calendar_event"]
    assert len(create_actions) == 0


def test_preprocessor_multi_pet_detection():
    """Pre-processor detects multiple pets in one message."""
    pet1 = _make_pet("三妹", pet_id=str(uuid.uuid4()))
    pet2 = _make_pet("豆豆", pet_id=str(uuid.uuid4()))

    actions = pre_process("三妹吃了狗粮，豆豆也吃了", [pet1, pet2], today=date(2026, 3, 24))
    pet_ids = {a.arguments.get("pet_id") for a in actions}
    assert str(pet1.id) in pet_ids or str(pet2.id) in pet_ids


# ============================================
# Test 12: Full Pipeline Integration
# ============================================
@pytest.mark.asyncio
async def test_full_pipeline_preprocessor_to_orchestrator():
    """Test the full flow: pre-process -> build prompt -> orchestrator -> result."""
    pet = _make_pet("三妹", pet_id="abc-123")
    message = "三妹吃了200克狗粮"
    today_str = "2026-03-24"

    actions = pre_process(message, [pet], today=date(2026, 3, 24))
    assert len(actions) >= 1

    emergency = detect_emergency(message)
    assert emergency.detected is False

    hints = [f"{a.tool_name}({json.dumps(a.arguments, ensure_ascii=False)})" for a in actions if a.confidence >= 0.5]
    system_prompt = build_system_prompt(
        pets=[pet],
        preprocessor_hints=hints if hints else None,
        today=today_str,
    )
    assert "三妹" in system_prompt

    tool_args = {
        "pet_id": "abc-123",
        "event_date": "2026-03-24",
        "title": "喂食200克狗粮",
        "category": "diet",
    }
    initial_chunks = _make_stream_chunks(
        tool_calls=[{"name": "create_calendar_event", "args": tool_args}]
    )
    followup_chunks = _make_stream_chunks(content="已记录~")

    call_count = 0

    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockAsyncIterator(initial_chunks)
        return MockAsyncIterator(followup_chunks)

    mock_execute = AsyncMock(
        return_value={"success": True, "card": {"type": "record"}}
    )
    mock_db = AsyncMock()
    cards = []

    with patch(
        "app.agents.orchestrator.litellm.acompletion",
        new_callable=AsyncMock,
        side_effect=mock_completion,
    ), patch("app.agents.orchestrator.validate_tool_args", return_value=[]), patch(
        "app.agents.orchestrator.execute_tool", mock_execute
    ):
        result = await run_orchestrator(
            message=message,
            system_prompt=system_prompt,
            context_messages=[{"role": "user", "content": message}],
            db=mock_db,
            user_id="user-1",
            on_card=lambda c: cards.append(c),
        )

    assert len(result.cards) == 1
    mock_execute.assert_called_once()


# ============================================
# Test 13: Orchestrator Error Recovery
# ============================================
@pytest.mark.asyncio
async def test_orchestrator_error_recovery():
    """LLM error -> orchestrator returns graceful error message."""
    tokens = []

    with patch(
        "app.agents.orchestrator.litellm.acompletion",
        new_callable=AsyncMock,
        side_effect=Exception("API rate limit exceeded"),
    ):
        result = await run_orchestrator(
            message="test",
            system_prompt="test",
            context_messages=[{"role": "user", "content": "test"}],
            on_token=lambda t: tokens.append(t),
        )

    assert "抱歉" in result.response_text or "错误" in result.response_text
    assert len(tokens) > 0


# ============================================
# Test 14: Nudge Mechanism
# ============================================
@pytest.mark.asyncio
async def test_nudge_fires_when_llm_skips_tools():
    """When pre-processor expects tools but LLM ignores, nudge triggers and LLM retries."""
    from app.agents.pre_processing.types import SuggestedAction

    # Round 1: LLM just chats (ignores tool intent)
    round1_chunks = _make_stream_chunks(content="好的~三妹吃狗粮啦")
    # Round 2 (after nudge): LLM calls tool
    tool_args = {"pet_id": "abc", "event_date": "2026-03-24", "title": "吃狗粮", "category": "diet"}
    round2_chunks = _make_stream_chunks(tool_calls=[{"name": "create_calendar_event", "args": tool_args}])
    # Round 3: follow-up
    round3_chunks = _make_stream_chunks(content="已记录")

    call_count = 0
    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockAsyncIterator(round1_chunks)
        elif call_count == 2:
            return MockAsyncIterator(round2_chunks)
        return MockAsyncIterator(round3_chunks)

    mock_execute = AsyncMock(return_value={"success": True, "card": {"type": "record"}})

    suggested = [SuggestedAction(
        tool_name="create_calendar_event",
        arguments=tool_args,
        confidence=0.9,
    )]

    with patch("app.agents.orchestrator.litellm.acompletion", new_callable=AsyncMock, side_effect=mock_completion), \
         patch("app.agents.orchestrator.validate_tool_args", return_value=[]), \
         patch("app.agents.orchestrator.execute_tool", mock_execute):
        result = await run_orchestrator(
            message="三妹吃了狗粮",
            system_prompt="test",
            context_messages=[{"role": "user", "content": "三妹吃了狗粮"}],
            db=AsyncMock(), user_id="user-1",
            suggested_actions=suggested,
        )

    assert call_count == 3  # initial + nudge + follow-up
    assert len(result.cards) == 1
    assert "create_calendar_event" in result.tools_called
