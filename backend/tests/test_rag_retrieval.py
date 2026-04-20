"""Tests for RAG retrieval logic (merge, threshold, intent boost)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _row(content, meta, distance):
    """Fake (Embedding, distance) row with a stable source_id so merge works."""
    emb = MagicMock(content=content, source_id=uuid.uuid4(), metadata_json=meta)
    return (emb, distance)


@pytest.fixture(autouse=True)
def _disable_expansion_and_intent(monkeypatch):
    """Baseline tests run with expansion + intent filter off.

    Each feature has its own dedicated test module. Core retrieval tests
    should exercise only the vector → threshold → merge path.
    """
    from app.config import settings
    monkeypatch.setattr(settings, "rag_enable_query_expansion", False)
    monkeypatch.setattr(settings, "rag_enable_intent_filter", False)


@pytest.mark.asyncio
async def test_retrieve_knowledge_returns_both_sources():
    kb_rows = [_row("犬呕吐常见原因...", {"title": "犬呕吐", "url": "https://example.com/vomit"}, 0.15)]
    history_rows = [_row("维尼拉肚子去了医院", {"date": "2026-03-15", "event_id": str(uuid.uuid4())}, 0.2)]

    mock_kb = MagicMock(); mock_kb.all.return_value = kb_rows
    mock_hist = MagicMock(); mock_hist.all.return_value = history_rows

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_kb, mock_hist])

    with patch("app.rag.retrieval.embed_texts", AsyncMock(return_value=[[0.1] * 1536])):
        from app.rag.retrieval import retrieve_knowledge
        result = await retrieve_knowledge(
            query="狗呕吐", db=mock_db, user_id=uuid.uuid4(),
            pet_id=uuid.uuid4(), species="dog",
        )

    assert len(result["knowledge"]) == 1
    assert result["knowledge"][0]["title"] == "犬呕吐"
    assert result["knowledge"][0]["distance"] == 0.15
    assert len(result["history"]) == 1


@pytest.mark.asyncio
async def test_retrieve_knowledge_drops_results_above_threshold():
    kb_rows = [
        _row("close match", {"title": "A"}, 0.2),
        _row("noise", {"title": "B"}, 0.9),
    ]
    mock_kb = MagicMock(); mock_kb.all.return_value = kb_rows
    mock_hist = MagicMock(); mock_hist.all.return_value = []
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_kb, mock_hist])

    with patch("app.rag.retrieval.embed_texts", AsyncMock(return_value=[[0.1] * 1536])):
        from app.rag.retrieval import retrieve_knowledge
        result = await retrieve_knowledge(query="q", db=mock_db, user_id=uuid.uuid4())

    titles = [k["title"] for k in result["knowledge"]]
    assert titles == ["A"]


@pytest.mark.asyncio
async def test_retrieve_knowledge_without_pet_id():
    mock_empty = MagicMock(); mock_empty.all.return_value = []
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_empty)

    with patch("app.rag.retrieval.embed_texts", AsyncMock(return_value=[[0.1] * 1536])):
        from app.rag.retrieval import retrieve_knowledge
        result = await retrieve_knowledge(
            query="疫苗", db=mock_db, user_id=uuid.uuid4(),
            pet_id=None, species="dog",
        )

    assert result["knowledge"] == []
    assert result["history"] == []


@pytest.mark.asyncio
async def test_intent_boost_runs_second_kb_search(monkeypatch):
    """'狗吃了巧克力' fires the toxin_food rule → extra title-constrained query.

    The main search returns a Foreign Objects false-positive; the boost search
    returns the correct Toxic Foods article at a better distance. The merged
    result should put Toxic Foods first.
    """
    from app.config import settings
    monkeypatch.setattr(settings, "rag_enable_intent_filter", True)

    main_rows = [_row("foreign-objects content", {"title": "Swallowed Foreign Objects in Dogs"}, 0.30)]
    boost_rows = [_row("toxic-foods content", {"title": "Toxic Foods for Dogs and Cats"}, 0.20)]
    history_rows = []

    mock_main = MagicMock(); mock_main.all.return_value = main_rows
    mock_boost = MagicMock(); mock_boost.all.return_value = boost_rows
    mock_hist = MagicMock(); mock_hist.all.return_value = history_rows

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_main, mock_boost, mock_hist])

    with patch("app.rag.retrieval.embed_texts", AsyncMock(return_value=[[0.1] * 1536])):
        from app.rag.retrieval import retrieve_knowledge
        result = await retrieve_knowledge(
            query="狗吃了巧克力", db=mock_db, user_id=uuid.uuid4(), species="dog",
        )

    titles = [k["title"] for k in result["knowledge"]]
    assert titles[0] == "Toxic Foods for Dogs and Cats"
    assert result["knowledge"][0]["distance"] == 0.20
    # Exactly 3 db.execute calls: main KB, boosted KB, history.
    assert mock_db.execute.await_count == 3
