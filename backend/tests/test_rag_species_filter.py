"""Smoke test: species filter excludes dog-only articles for a cat owner.

Verifies the SQL `WHERE` clause emitted by `_search_kb` includes an OR
over species==<user_species> / species=='all', so that a cat active pet
cannot retrieve embeddings tagged species='dog'.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _disable_expansion_and_intent(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "rag_enable_query_expansion", False)
    monkeypatch.setattr(settings, "rag_enable_intent_filter", False)


@pytest.mark.asyncio
async def test_cat_query_filters_out_dog_only_articles():
    """Simulate KB containing dog-only + cat + all-species rows.

    The retrieval SQL should filter dog-only rows out before results reach
    the caller. Here we assert that the species filter is applied in the
    query by inspecting captured SQL compilation.
    """

    def _row(title, species_tag, distance):
        emb = MagicMock(
            content=f"content for {title}",
            source_id=uuid.uuid4(),
            metadata_json={"title": title, "species": species_tag},
        )
        return (emb, distance)

    cat_and_all = [
        _row("Cat Vomiting", "cat", 0.15),
        _row("General Vomiting (all species)", "all", 0.18),
    ]
    mock_kb = MagicMock(); mock_kb.all.return_value = cat_and_all
    mock_hist = MagicMock(); mock_hist.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_kb, mock_hist])

    with patch("app.rag.retrieval.embed_texts", AsyncMock(return_value=[[0.1] * 1536])):
        from app.rag.retrieval import retrieve_knowledge
        result = await retrieve_knowledge(
            query="vomiting", db=mock_db, user_id=uuid.uuid4(),
            pet_id=uuid.uuid4(), species="cat",
        )

    titles = [k["title"] for k in result["knowledge"]]
    assert "Cat Vomiting" in titles
    assert "General Vomiting (all species)" in titles
    assert not any("Dog" in t for t in titles)

    kb_call = mock_db.execute.await_args_list[0]
    compiled = str(kb_call.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "species" in compiled
    assert "'cat'" in compiled
    assert "'all'" in compiled


@pytest.mark.asyncio
async def test_species_auto_resolved_from_pet_id_when_llm_omits_it():
    """If LLM calls search_knowledge without `species`, the tool should look
    up the pet's species from pet_id and pass it to retrieve_knowledge."""
    from app.agents.tools import knowledge as knowledge_tool

    user_id = uuid.uuid4()
    pet_id = uuid.uuid4()

    fake_pet = MagicMock()
    fake_pet.user_id = user_id
    fake_pet.species = MagicMock(value="cat")

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=fake_pet)

    captured = {}

    async def fake_retrieve(**kwargs):
        captured.update(kwargs)
        return {"knowledge": [], "history": []}

    with patch.object(knowledge_tool, "retrieve_knowledge", fake_retrieve):
        await knowledge_tool.search_knowledge(
            arguments={"query": "vomiting", "pet_id": str(pet_id)},
            db=mock_db,
            user_id=user_id,
        )

    assert captured["species"] == "cat"
