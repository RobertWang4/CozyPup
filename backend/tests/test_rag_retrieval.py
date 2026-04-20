"""Tests for RAG retrieval logic."""

import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _row(content, meta, distance):
    """Fake (Embedding, distance) row returned by select(Embedding, distance)."""
    emb = MagicMock(content=content, source_id=uuid.uuid4(), metadata_json=meta)
    return (emb, distance)


@pytest.mark.asyncio
async def test_retrieve_knowledge_returns_both_sources():
    """retrieve should return knowledge + history lists."""
    mock_embed = AsyncMock(return_value=[0.1] * 1536)

    kb_rows = [_row("犬呕吐常见原因...", {"title": "犬呕吐", "url": "https://example.com/vomit"}, 0.15)]
    history_rows = [_row("维尼拉肚子去了医院", {"date": "2026-03-15", "event_id": str(uuid.uuid4())}, 0.2)]

    mock_result_kb = MagicMock()
    mock_result_kb.all.return_value = kb_rows
    mock_result_history = MagicMock()
    mock_result_history.all.return_value = history_rows

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

    assert len(result["knowledge"]) == 1
    assert result["knowledge"][0]["title"] == "犬呕吐"
    assert result["knowledge"][0]["distance"] == 0.15
    assert len(result["history"]) == 1


@pytest.mark.asyncio
async def test_retrieve_knowledge_drops_results_above_threshold():
    """Results exceeding rag_distance_threshold should be filtered out."""
    mock_embed = AsyncMock(return_value=[0.1] * 1536)

    kb_rows = [
        _row("close match", {"title": "A"}, 0.2),
        _row("noise", {"title": "B"}, 0.9),
    ]
    mock_result = MagicMock()
    mock_result.all.return_value = kb_rows
    mock_empty = MagicMock()
    mock_empty.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_result, mock_empty])

    with patch("app.rag.retrieval.embed_text", mock_embed):
        from app.rag.retrieval import retrieve_knowledge
        result = await retrieve_knowledge(
            query="q", db=mock_db, user_id=uuid.uuid4(),
        )

    titles = [k["title"] for k in result["knowledge"]]
    assert titles == ["A"]


@pytest.mark.asyncio
async def test_retrieve_knowledge_without_pet_id():
    """When pet_id is None, should still query history for all user's pets."""
    mock_embed = AsyncMock(return_value=[0.1] * 1536)
    mock_result = MagicMock()
    mock_result.all.return_value = []

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
