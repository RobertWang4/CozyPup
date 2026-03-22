import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.rag.assembler import assemble_rag_context, _deduplicate, _truncate_by_budget, _format_context
from app.rag.base import RetrievalResult


class TestDeduplicate:
    def test_keeps_summary_over_turn_same_date_when_summary_scores_higher(self):
        results = [
            RetrievalResult("summary of day", "daily_summary", "1", 0.8, {"session_date": "2026-03-20"}),
            RetrievalResult("User: hi\nAssistant: hello", "chat_turn", "2", 0.75, {"session_date": "2026-03-20"}),
        ]
        deduped = _deduplicate(results)
        assert len(deduped) == 1
        assert deduped[0].source_type == "daily_summary"

    def test_keeps_turn_if_higher_score_than_summary(self):
        results = [
            RetrievalResult("summary", "daily_summary", "1", 0.5, {"session_date": "2026-03-20"}),
            RetrievalResult("very relevant turn", "chat_turn", "2", 0.95, {"session_date": "2026-03-20"}),
        ]
        deduped = _deduplicate(results)
        assert len(deduped) == 2  # Both kept because turn scores higher

    def test_keeps_both_if_different_dates(self):
        results = [
            RetrievalResult("summary", "daily_summary", "1", 0.8, {"session_date": "2026-03-20"}),
            RetrievalResult("turn", "chat_turn", "2", 0.75, {"session_date": "2026-03-19"}),
        ]
        deduped = _deduplicate(results)
        assert len(deduped) == 2

    def test_keeps_turn_if_no_summary_for_date(self):
        results = [
            RetrievalResult("turn", "chat_turn", "1", 0.9, {"session_date": "2026-03-20"}),
        ]
        deduped = _deduplicate(results)
        assert len(deduped) == 1


class TestTruncateByBudget:
    def test_truncates_within_budget(self):
        results = [
            RetrievalResult("a" * 100, "chat_turn", "1", 0.9, {}),
            RetrievalResult("b" * 100, "chat_turn", "2", 0.8, {}),
            RetrievalResult("c" * 100, "chat_turn", "3", 0.7, {}),
        ]
        # Budget of 100 tokens ~ 200 chars -> should keep first 2
        truncated = _truncate_by_budget(results, max_tokens=100)
        assert len(truncated) <= 2

    def test_empty_input(self):
        assert _truncate_by_budget([], max_tokens=1000) == []


class TestFormatContext:
    def test_formats_chat_and_calendar(self):
        results = [
            RetrievalResult("summary of 3/20", "daily_summary", "1", 0.9, {"session_date": "2026-03-20"}),
            RetrievalResult("2026-03-21 [diet] Fed 200g", "calendar_event", "2", 0.8, {"event_date": "2026-03-21"}),
        ]
        formatted = _format_context(results)
        assert "Relevant History" in formatted
        assert "summary of 3/20" in formatted
        assert "Fed 200g" in formatted

    def test_empty_returns_empty_string(self):
        assert _format_context([]) == ""


class TestAssembleRagContext:
    @pytest.mark.asyncio
    async def test_returns_formatted_context(self):
        fake_embedding = [0.1] * 1536
        fake_chat_results = [
            RetrievalResult("conversation about food", "chat_turn", "1", 0.85, {"session_date": "2026-03-20"}),
        ]
        fake_cal_results = [
            RetrievalResult("2026-03-20 [diet] Fed 200g", "calendar_event", "2", 0.9, {"event_date": "2026-03-20"}),
        ]

        with patch("app.rag.assembler.get_embedding_service") as mock_emb, \
             patch("app.rag.assembler._chat_retriever") as mock_chat, \
             patch("app.rag.assembler._calendar_retriever") as mock_cal, \
             patch("app.rag.assembler.ensure_yesterday_summary", new_callable=AsyncMock):
            mock_emb.return_value.embed = AsyncMock(return_value=fake_embedding)
            mock_chat.retrieve = AsyncMock(return_value=fake_chat_results)
            mock_cal.retrieve = AsyncMock(return_value=fake_cal_results)

            result = await assemble_rag_context("豆豆吃了什么", uuid.uuid4())

        assert "conversation about food" in result
        assert "Fed 200g" in result

    @pytest.mark.asyncio
    async def test_returns_empty_on_embedding_failure(self):
        with patch("app.rag.assembler.get_embedding_service") as mock_emb, \
             patch("app.rag.assembler.ensure_yesterday_summary", new_callable=AsyncMock):
            mock_emb.return_value.embed = AsyncMock(return_value=None)

            result = await assemble_rag_context("test", uuid.uuid4())

        assert result == ""
