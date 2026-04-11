"""Tests for RAG retrieval logic."""

import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_retrieve_knowledge_returns_both_sources():
    """retrieve should return knowledge + history lists."""
    mock_embed = AsyncMock(return_value=[0.1] * 1536)

    mock_kb_rows = [
        MagicMock(
            content="犬呕吐常见原因...",
            source_id=uuid.uuid4(),
            metadata_json={"title": "犬呕吐", "url": "https://example.com/vomit"},
        )
    ]
    mock_history_rows = [
        MagicMock(
            content="维尼拉肚子去了医院",
            source_id=uuid.uuid4(),
            metadata_json={"date": "2026-03-15", "event_id": str(uuid.uuid4())},
        )
    ]

    mock_result_kb = MagicMock()
    mock_result_kb.scalars.return_value.all.return_value = mock_kb_rows
    mock_result_history = MagicMock()
    mock_result_history.scalars.return_value.all.return_value = mock_history_rows

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_result_kb, mock_result_history])

    with patch("app.rag.retrieval.embed_text", mock_embed):
        from app.rag.retrieval import retrieve_knowledge
        result = await retrieve_knowledge(
            query="狗呕吐",
            db=mock_db,
            user_id=uuid.uuid4(),
            pet_id=uuid.uuid4(),
            species="dog",
        )

    assert "knowledge" in result
    assert "history" in result
    assert len(result["knowledge"]) == 1
    assert result["knowledge"][0]["title"] == "犬呕吐"
    assert len(result["history"]) == 1


@pytest.mark.asyncio
async def test_retrieve_knowledge_without_pet_id():
    """When pet_id is None, should still query history for all user's pets."""
    mock_embed = AsyncMock(return_value=[0.1] * 1536)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("app.rag.retrieval.embed_text", mock_embed):
        from app.rag.retrieval import retrieve_knowledge
        result = await retrieve_knowledge(
            query="疫苗",
            db=mock_db,
            user_id=uuid.uuid4(),
            pet_id=None,
            species="dog",
        )

    assert result["knowledge"] == []
    assert result["history"] == []
