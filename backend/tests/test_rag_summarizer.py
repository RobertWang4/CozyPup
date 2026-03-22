import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.rag.summarizer import ensure_yesterday_summary


class TestEnsureYesterdaySummary:
    @pytest.mark.asyncio
    async def test_skips_if_summary_exists(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()  # summary exists
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.rag.summarizer.async_session", return_value=mock_session_ctx):
            await ensure_yesterday_summary(uuid.uuid4())

        # Should not have called LLM
        # (only one db.execute call — the check query)
        assert mock_db.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_skips_if_no_yesterday_session(self):
        mock_db = AsyncMock()
        mock_result_summary = MagicMock()
        mock_result_summary.scalar_one_or_none.return_value = None  # no summary

        mock_result_session = MagicMock()
        mock_result_session.scalar_one_or_none.return_value = None  # no session yesterday

        mock_db.execute = AsyncMock(side_effect=[mock_result_summary, mock_result_session])

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.rag.summarizer.async_session", return_value=mock_session_ctx):
            await ensure_yesterday_summary(uuid.uuid4())

        # Check + session query, no LLM call
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_silently_handles_errors(self):
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.rag.summarizer.async_session", return_value=mock_session_ctx):
            # Should not raise
            await ensure_yesterday_summary(uuid.uuid4())
