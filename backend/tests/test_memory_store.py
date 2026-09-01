import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.memory import MemoryNodeType
from app.memory.store import (
    delete_memory_for_source,
    upsert_behavioral_memory,
    upsert_knowledge_memory,
)


@pytest.mark.asyncio
async def test_upsert_behavioral_memory_adds_memweaver_node():
    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    async def fake_embed(text):
        assert "维尼今天吐了" in text
        return [0.1] * 1536

    await upsert_behavioral_memory(
        db=mock_db,
        user_id=uuid.uuid4(),
        source_kind="chat_turn",
        source_id=uuid.uuid4(),
        content="维尼今天吐了",
        pet_id=uuid.uuid4(),
        metadata={"date": "2026-06-13"},
        embed=fake_embed,
    )

    mock_db.add.assert_called_once()
    added = mock_db.add.call_args[0][0]
    assert added.node_type == MemoryNodeType.behavioral
    assert added.source_kind == "chat_turn"
    assert added.content == "维尼今天吐了"
    assert added.embedding == [0.1] * 1536
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_knowledge_memory_adds_global_knowledge_node():
    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    await upsert_knowledge_memory(
        db=mock_db,
        title="Dog Vomiting",
        content="Repeated vomiting can require vet care.",
        species="dog",
        category="digestive",
        url="https://example.com",
        embed=AsyncMock(return_value=[0.2] * 1536),
    )

    added = mock_db.add.call_args[0][0]
    assert added.user_id is None
    assert added.node_type == MemoryNodeType.knowledge
    assert added.title == "Dog Vomiting"
    assert added.metadata_json["species"] == "dog"


@pytest.mark.asyncio
async def test_delete_memory_for_source_deletes_nodes_and_edges():
    mock_db = AsyncMock()

    await delete_memory_for_source(
        db=mock_db,
        source_kind="calendar_event",
        source_id=uuid.uuid4(),
    )

    assert mock_db.execute.call_count == 2
    mock_db.commit.assert_called_once()
