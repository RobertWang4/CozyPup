"""Integration tests for RAG pipeline — uses mocks for embedding/LLM, tests full flow."""

import json
import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.rag.assembler import assemble_rag_context
from app.rag.intent import needs_retrieval


class TestRagIntegration:
    @pytest.mark.asyncio
    async def test_rag_skipped_for_recording(self):
        """Recording messages skip RAG entirely."""
        assert needs_retrieval("豆豆今天吃了200克") is False

    @pytest.mark.asyncio
    async def test_rag_returns_empty_on_embedding_failure(self):
        """If embedding fails, RAG returns empty string (graceful degradation)."""
        with patch("app.rag.assembler.get_embedding_service") as mock_emb, \
             patch("app.rag.assembler.ensure_yesterday_summary", new_callable=AsyncMock):
            mock_emb.return_value.embed = AsyncMock(return_value=None)

            result = await assemble_rag_context("豆豆怎么样", uuid.uuid4())

        assert result == ""

    @pytest.mark.asyncio
    async def test_rag_returns_empty_when_no_results(self):
        """If retrievers return nothing, RAG returns empty string."""
        with patch("app.rag.assembler.get_embedding_service") as mock_emb, \
             patch("app.rag.assembler._chat_retriever") as mock_chat, \
             patch("app.rag.assembler._calendar_retriever") as mock_cal, \
             patch("app.rag.assembler.ensure_yesterday_summary", new_callable=AsyncMock):
            mock_emb.return_value.embed = AsyncMock(return_value=[0.1] * 1536)
            mock_chat.retrieve = AsyncMock(return_value=[])
            mock_cal.retrieve = AsyncMock(return_value=[])

            result = await assemble_rag_context("豆豆怎么样", uuid.uuid4())

        assert result == ""

    @pytest.mark.asyncio
    async def test_prompt_format_with_empty_rag(self):
        """System prompt works correctly when rag_context is empty."""
        from app.agents.prompts import CHAT_SYSTEM_PROMPT

        formatted = CHAT_SYSTEM_PROMPT.format(
            pet_context="Test pet context",
            today_date="2026-03-22",
            rag_context="",
        )
        assert "Test pet context" in formatted
        assert "{rag_context}" not in formatted

    @pytest.mark.asyncio
    async def test_prompt_format_with_rag(self):
        """System prompt includes RAG context when provided."""
        from app.agents.prompts import CHAT_SYSTEM_PROMPT

        rag = "## Relevant History\n- [2026-03-20] Doudu ate 200g"
        formatted = CHAT_SYSTEM_PROMPT.format(
            pet_context="Test pet context",
            today_date="2026-03-22",
            rag_context=rag,
        )
        assert "Relevant History" in formatted
        assert "Doudu ate 200g" in formatted
