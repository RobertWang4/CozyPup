import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.agents.context_agent import summarize_context, should_summarize


@pytest.mark.asyncio
async def test_summarize_context_basic():
    """Test that summarize_context returns correct structure."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"topics": ["喂食"], "pending": null, "mood": "开心", "key_facts": ["三妹吃了200g狗粮"]}'

    with patch("app.agents.context_agent.litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
        result = await summarize_context([
            {"role": "user", "content": "三妹今天吃了200g狗粮"},
            {"role": "assistant", "content": "已记录三妹的饮食"}
        ])

    assert "topics" in result
    assert isinstance(result["topics"], list)
    assert "key_facts" in result
    assert isinstance(result["key_facts"], list)
    assert "mood" in result


@pytest.mark.asyncio
async def test_summarize_with_previous_summary():
    """Test that previous summary is included in context."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"topics": ["喂食", "散步"], "pending": "明天带三妹去医院", "mood": "正常", "key_facts": ["三妹吃了狗粮", "下午遛了三妹"]}'

    with patch("app.agents.context_agent.litellm.acompletion", new_callable=AsyncMock, return_value=mock_response) as mock_call:
        previous = {"topics": ["喂食"], "key_facts": ["早上喂了三妹"]}
        result = await summarize_context(
            [{"role": "user", "content": "下午遛了三妹"}],
            previous_summary=previous,
        )

        # Verify previous summary was passed to LLM
        call_args = mock_call.call_args
        user_msg = call_args[1]["messages"][1]["content"]
        assert "上次摘要" in user_msg


@pytest.mark.asyncio
async def test_summarize_handles_error():
    """Test graceful fallback on LLM error."""
    with patch("app.agents.context_agent.litellm.acompletion", new_callable=AsyncMock, side_effect=Exception("API error")):
        result = await summarize_context([{"role": "user", "content": "test"}])

    assert result["topics"] == []
    assert result["mood"] == "unknown"


def test_should_summarize():
    """Test threshold logic."""
    assert should_summarize(total_messages=6, summarized_up_to=0) is True
    assert should_summarize(total_messages=5, summarized_up_to=0) is True
    assert should_summarize(total_messages=4, summarized_up_to=0) is False
    assert should_summarize(total_messages=10, summarized_up_to=5) is True
    assert should_summarize(total_messages=7, summarized_up_to=5) is False
    assert should_summarize(total_messages=5, summarized_up_to=None) is True
