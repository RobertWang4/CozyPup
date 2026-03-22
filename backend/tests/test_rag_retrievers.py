import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.rag.base import RetrievalResult
from app.rag.chat_retriever import ChatHistoryRetriever
from app.rag.calendar_retriever import CalendarRetriever


class TestChatHistoryRetriever:
    @pytest.mark.asyncio
    async def test_retrieve_returns_results(self):
        fake_rows = [
            MagicMock(
                content="User: 豆豆吃了多少\nAssistant: 200g",
                source_type="chat_turn",
                source_id=uuid.uuid4(),
                metadata_json={"session_date": "2026-03-20"},
                _cosine_distance=0.15,
            ),
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = fake_rows
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.rag.chat_retriever.async_session", return_value=mock_session_ctx):
            retriever = ChatHistoryRetriever()
            results = await retriever.retrieve(
                query_embedding=[0.1] * 1536,
                user_id=uuid.uuid4(),
                top_k=5,
            )

        assert len(results) == 1
        assert results[0].source_type == "chat_turn"

    @pytest.mark.asyncio
    async def test_retrieve_returns_empty_on_error(self):
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(side_effect=Exception("DB error"))
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.rag.chat_retriever.async_session", return_value=mock_session_ctx):
            retriever = ChatHistoryRetriever()
            results = await retriever.retrieve([0.1] * 1536, uuid.uuid4())

        assert results == []


class TestCalendarRetriever:
    @pytest.mark.asyncio
    async def test_retrieve_returns_results(self):
        pet_id = uuid.uuid4()
        fake_rows = [
            MagicMock(
                content="2026-03-20 [diet] Fed 200g",
                source_type="calendar_event",
                source_id=uuid.uuid4(),
                pet_id=pet_id,
                metadata_json={"event_date": "2026-03-20", "category": "diet"},
                _cosine_distance=0.1,
            ),
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = fake_rows

        # Second query for context expansion
        mock_expansion_result = MagicMock()
        mock_expansion_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_result, mock_expansion_result])

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.rag.calendar_retriever.async_session", return_value=mock_session_ctx):
            retriever = CalendarRetriever()
            results = await retriever.retrieve(
                query_embedding=[0.1] * 1536,
                user_id=uuid.uuid4(),
                top_k=5,
            )

        assert len(results) >= 1
        assert results[0].source_type == "calendar_event"
