from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from app.memory import KnowledgeSnippet, MemorySnippet, RetrievedContext


def test_agent_runtime_paths_do_not_import_app_rag():
    repo = Path(__file__).resolve().parents[1]
    runtime_files = [
        repo / "app" / "routers" / "chat.py",
        repo / "app" / "routers" / "calendar.py",
        repo / "app" / "agents" / "tool_memory.py",
        repo / "app" / "agents" / "tools" / "knowledge.py",
    ]

    for path in runtime_files:
        assert "app.rag" not in path.read_text()


@pytest.mark.asyncio
async def test_search_knowledge_uses_memweaver_context_and_preserves_response_shape():
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
        return RetrievedContext(
            behavioral_memories=[
                MemorySnippet(
                    kind="behavioral",
                    content="维尼昨天吐了两次",
                    date="2026-06-12",
                    entity_id="event-1",
                    score=0.12,
                )
            ],
            knowledge_snippets=[
                KnowledgeSnippet(
                    title="Cat Vomiting",
                    content="Repeated vomiting can require vet care.",
                    url="https://example.com",
                    score=0.2,
                )
            ],
        )

    with patch.object(knowledge_tool, "retrieve_memweaver_context", fake_retrieve):
        result = await knowledge_tool.search_knowledge(
            arguments={"query": "vomiting", "pet_id": str(pet_id)},
            db=mock_db,
            user_id=user_id,
        )

    assert captured["species"] == "cat"
    assert result["success"] is True
    assert result["knowledge"][0]["title"] == "Cat Vomiting"
    assert result["history"][0]["content"] == "维尼昨天吐了两次"
    assert result["card"]["type"] == "references"
