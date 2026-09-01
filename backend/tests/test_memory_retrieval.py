import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.memory import MemoryNodeType
from app.memory.retrieval import _search_nodes, retrieve_memweaver_context


@pytest.mark.asyncio
async def test_retrieve_memweaver_context_returns_hierarchical_memory():
    now = datetime(2026, 6, 13, tzinfo=UTC)
    recent_id = uuid.uuid4()

    async def fake_embed(text):
        assert text == "维尼又吐了怎么办"
        return [0.1] * 1536

    async def fake_search_nodes(**kwargs):
        assert kwargs["user_id"] == user_id
        assert kwargs["pet_id"] == pet_id
        assert kwargs["species"] == "dog"
        older = SimpleNamespace(
            id=uuid.uuid4(),
            node_type=MemoryNodeType.behavioral,
            source_id=uuid.uuid4(),
            title="older",
            content="维尼去年吐过一次",
            occurred_at=now - timedelta(days=300),
            metadata_json={"date": "2025-08-01"},
        )
        recent = SimpleNamespace(
            id=recent_id,
            node_type=MemoryNodeType.behavioral,
            source_id=uuid.uuid4(),
            title="recent",
            content="维尼昨天吐了两次",
            occurred_at=now - timedelta(days=1),
            metadata_json={"date": "2026-06-12"},
        )
        cognitive = SimpleNamespace(
            id=uuid.uuid4(),
            node_type=MemoryNodeType.cognitive,
            source_id=uuid.uuid4(),
            title="sensitive stomach",
            content="维尼肠胃比较敏感",
            occurred_at=None,
            metadata_json={},
        )
        knowledge = SimpleNamespace(
            id=uuid.uuid4(),
            node_type=MemoryNodeType.knowledge,
            source_id=uuid.uuid4(),
            title="Vomiting",
            content="Watch dehydration.",
            occurred_at=None,
            metadata_json={"url": "https://example.com", "species": "dog"},
        )
        return {
            "user": [(older, 0.21), (recent, 0.22), (cognitive, 0.18)],
            "knowledge": [(knowledge, 0.2)],
        }

    user_id = uuid.uuid4()
    pet_id = uuid.uuid4()

    context = await retrieve_memweaver_context(
        query="维尼又吐了怎么办",
        db=object(),
        user_id=user_id,
        pet_id=pet_id,
        species="dog",
        embed=fake_embed,
        search_nodes=fake_search_nodes,
        now=now,
    )

    assert context.behavioral_memories[0].content == "维尼昨天吐了两次"
    assert context.behavioral_memories[0].date == "2026-06-12"
    assert context.cognitive_memories[0].content == "维尼肠胃比较敏感"
    assert context.knowledge_snippets[0].title == "Vomiting"
    assert context.knowledge_snippets[0].url == "https://example.com"


@pytest.mark.asyncio
async def test_retrieve_memweaver_context_can_skip_knowledge():
    async def fake_embed(text):
        return [0.1] * 1536

    async def fake_search_nodes(**kwargs):
        return {
            "user": [
                (
                    SimpleNamespace(
                        id=uuid.uuid4(),
                        node_type=MemoryNodeType.behavioral,
                        source_id=uuid.uuid4(),
                        title="weight",
                        content="维尼最近体重 8kg",
                        occurred_at=None,
                        metadata_json={},
                    ),
                    0.1,
                )
            ],
            "knowledge": [
                (
                    SimpleNamespace(
                        id=uuid.uuid4(),
                        node_type=MemoryNodeType.knowledge,
                        source_id=uuid.uuid4(),
                        title="Weight",
                        content="general article",
                        occurred_at=None,
                        metadata_json={},
                    ),
                    0.2,
                )
            ],
        }

    context = await retrieve_memweaver_context(
        query="维尼最近体重多少",
        db=object(),
        user_id=uuid.uuid4(),
        include_knowledge=False,
        embed=fake_embed,
        search_nodes=fake_search_nodes,
    )

    assert len(context.behavioral_memories) == 1
    assert context.knowledge_snippets == []


@pytest.mark.asyncio
async def test_search_nodes_executes_one_sql_for_user_memory_and_knowledge():
    behavioral = SimpleNamespace(node_type=MemoryNodeType.behavioral)
    knowledge = SimpleNamespace(node_type=MemoryNodeType.knowledge)
    result = MagicMock()
    result.all.return_value = [(behavioral, 0.1), (knowledge, 0.2)]
    db = SimpleNamespace(execute=AsyncMock(return_value=result))

    rows = await _search_nodes(
        db=db,
        query_embedding=[0.1] * 1536,
        user_id=uuid.uuid4(),
        pet_id=None,
        species="dog",
        include_knowledge=True,
    )

    assert db.execute.await_count == 1
    assert rows["user"] == [(behavioral, 0.1)]
    assert rows["knowledge"] == [(knowledge, 0.2)]


@pytest.mark.asyncio
async def test_search_nodes_uses_union_all_not_window_ranking():
    captured = {}

    class Result:
        def all(self):
            return []

    class CaptureDb:
        async def execute(self, stmt):
            captured["sql"] = str(stmt.compile(dialect=postgresql.dialect()))
            return Result()

    await _search_nodes(
        db=CaptureDb(),
        query_embedding=[0.1] * 1536,
        user_id=uuid.uuid4(),
        pet_id=None,
        species="dog",
        include_knowledge=True,
    )

    assert "UNION ALL" in captured["sql"].upper()
    assert "row_number" not in captured["sql"].lower()


def test_memory_retrieval_does_not_import_rag():
    import inspect
    import app.memory.retrieval as retrieval

    assert "app.rag" not in inspect.getsource(retrieval)
