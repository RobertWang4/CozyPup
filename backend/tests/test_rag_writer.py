import uuid
from datetime import date
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.rag.writer import write_chat_turn, write_calendar_event


class TestWriteChatTurn:
    @pytest.mark.asyncio
    async def test_writes_embedding_to_db(self):
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        fake_embedding = [0.1] * 1536

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.rag.writer.get_embedding_service") as mock_svc, \
             patch("app.rag.writer.async_session", return_value=mock_session_ctx):
            mock_svc.return_value.embed = AsyncMock(return_value=fake_embedding)

            await write_chat_turn(
                user_id=user_id,
                session_id=session_id,
                user_msg="豆豆吃了多少",
                assistant_msg="根据记录...",
                session_date=date(2026, 3, 22),
            )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_on_embedding_failure(self):
        with patch("app.rag.writer.get_embedding_service") as mock_svc:
            mock_svc.return_value.embed = AsyncMock(return_value=None)

            # Should not raise
            await write_chat_turn(
                user_id=uuid.uuid4(),
                session_id=uuid.uuid4(),
                user_msg="test",
                assistant_msg="test",
                session_date=date(2026, 3, 22),
            )


class TestWriteCalendarEvent:
    @pytest.mark.asyncio
    async def test_writes_event_embedding(self):
        user_id = uuid.uuid4()
        pet_id = uuid.uuid4()
        event_id = uuid.uuid4()
        fake_embedding = [0.2] * 1536

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.rag.writer.get_embedding_service") as mock_svc, \
             patch("app.rag.writer.async_session", return_value=mock_session_ctx):
            mock_svc.return_value.embed = AsyncMock(return_value=fake_embedding)

            await write_calendar_event(
                user_id=user_id,
                pet_id=pet_id,
                event_id=event_id,
                event_date=date(2026, 3, 22),
                category="diet",
                title="Fed 200g kibble",
                raw_text="喂了200克狗粮",
            )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
