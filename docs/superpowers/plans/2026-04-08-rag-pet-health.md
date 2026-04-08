# RAG 宠物健康问答 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add RAG-powered pet health Q&A — LLM calls `search_knowledge` tool to retrieve external knowledge + user history, enabling guided diagnosis with references.

**Architecture:** Single `search_knowledge` tool queries two indexes in parallel (global knowledge base + user-scoped history). Embeddings generated via OpenAI text-embedding-3-small through LiteLLM. User history embeddings written async in chat post-processing. References displayed as a card button → bottom drawer on iOS.

**Tech Stack:** pgvector (existing), LiteLLM embedding API, FastAPI, SwiftUI

---

### Task 1: Add KnowledgeArticle model + extend SourceType enum

**Files:**
- Modify: `backend/app/models.py`

- [ ] **Step 1: Add `knowledge_base` to SourceType enum**

In `backend/app/models.py`, add `knowledge_base` to the existing `SourceType` enum:

```python
class SourceType(str, enum.Enum):
    chat_turn = "chat_turn"
    daily_summary = "daily_summary"
    calendar_event = "calendar_event"
    knowledge_base = "knowledge_base"
```

- [ ] **Step 2: Make Embedding.user_id nullable**

The `Embedding` model currently requires `user_id`. Knowledge base entries are global (no user). Change:

```python
# Before
user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

# After
user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
```

- [ ] **Step 3: Add KnowledgeArticle model**

Add after the `Embedding` class in `backend/app/models.py`:

```python
class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    species: Mapped[str] = mapped_column(String(20), nullable=False, default="all")
    url: Mapped[str | None] = mapped_column(String(2000))
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 4: Create migration**

```bash
cd backend
alembic revision --autogenerate -m "add knowledge_articles and extend source_type"
```

Review the generated migration, then apply:

```bash
alembic upgrade head
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/
git commit -m "feat: add KnowledgeArticle model and extend SourceType enum"
```

---

### Task 2: Embedding generation module

**Files:**
- Create: `backend/app/rag/__init__.py`
- Create: `backend/app/rag/embeddings.py`
- Test: `backend/tests/test_rag_embeddings.py`

- [ ] **Step 1: Create rag package**

Create `backend/app/rag/__init__.py`:

```python
"""RAG: Retrieval-Augmented Generation for pet health Q&A."""
```

- [ ] **Step 2: Write failing test for embed_text**

Create `backend/tests/test_rag_embeddings.py`:

```python
"""Tests for RAG embedding generation."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_embed_text_returns_1536_dim_vector():
    """embed_text should return a list of 1536 floats."""
    mock_response = AsyncMock()
    mock_response.data = [AsyncMock(embedding=[0.1] * 1536)]

    with patch("litellm.aembedding", return_value=mock_response) as mock_embed:
        from app.rag.embeddings import embed_text
        result = await embed_text("狗狗呕吐了")

        assert len(result) == 1536
        assert all(isinstance(v, float) for v in result)
        mock_embed.assert_called_once()


@pytest.mark.asyncio
async def test_embed_text_passes_model_and_api_config():
    """embed_text should use the configured embedding model and API base."""
    mock_response = AsyncMock()
    mock_response.data = [AsyncMock(embedding=[0.0] * 1536)]

    with patch("litellm.aembedding", return_value=mock_response) as mock_embed:
        from app.rag.embeddings import embed_text
        await embed_text("test query")

        call_kwargs = mock_embed.call_args[1]
        assert "model" in call_kwargs
        assert call_kwargs["input"] == ["test query"]
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && pytest tests/test_rag_embeddings.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.rag.embeddings'`

- [ ] **Step 4: Implement embed_text**

Create `backend/app/rag/embeddings.py`:

```python
"""Generate embeddings via LiteLLM (OpenAI text-embedding-3-small)."""

import logging

import litellm

from app.agents import llm_extra_kwargs
from app.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "openai/text-embedding-3-small"


async def embed_text(text: str) -> list[float]:
    """Generate a 1536-dim embedding for a single text string."""
    response = await litellm.aembedding(
        model=EMBEDDING_MODEL,
        input=[text],
        **llm_extra_kwargs(),
    )
    return response.data[0].embedding
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend && pytest tests/test_rag_embeddings.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/rag/ backend/tests/test_rag_embeddings.py
git commit -m "feat: add embedding generation module via LiteLLM"
```

---

### Task 3: Vector retrieval module

**Files:**
- Create: `backend/app/rag/retrieval.py`
- Test: `backend/tests/test_rag_retrieval.py`

- [ ] **Step 1: Write failing test for retrieve_knowledge**

Create `backend/tests/test_rag_retrieval.py`:

```python
"""Tests for RAG retrieval logic."""

import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_retrieve_knowledge_returns_both_sources():
    """retrieve should return knowledge + history lists."""
    mock_embed = AsyncMock(return_value=[0.1] * 1536)

    # Mock DB session with two queries (knowledge + history)
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_rag_retrieval.py -v
```

Expected: FAIL — module not found

- [ ] **Step 3: Implement retrieve_knowledge**

Create `backend/app/rag/retrieval.py`:

```python
"""Vector similarity retrieval for knowledge base and user history."""

import logging
import uuid

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Embedding, SourceType, KnowledgeArticle
from app.rag.embeddings import embed_text

logger = logging.getLogger(__name__)

TOP_K = 3


async def retrieve_knowledge(
    query: str,
    db: AsyncSession,
    user_id: uuid.UUID,
    pet_id: uuid.UUID | None = None,
    species: str | None = None,
) -> dict:
    """Retrieve relevant knowledge + user history via vector similarity.

    Returns:
        {
            "knowledge": [{"title": ..., "content": ..., "url": ...}],
            "history": [{"date": ..., "content": ..., "event_id": ...}],
        }
    """
    query_embedding = await embed_text(query)

    # 1. Search global knowledge base
    kb_filters = [Embedding.source_type == SourceType.knowledge_base]
    if species:
        # Filter by species via metadata_json — articles store species there
        # Also include "all" species articles
        kb_filters.append(
            or_(
                Embedding.metadata_json["species"].as_string() == species,
                Embedding.metadata_json["species"].as_string() == "all",
            )
        )

    kb_query = (
        select(Embedding)
        .where(and_(*kb_filters))
        .order_by(Embedding.embedding.cosine_distance(query_embedding))
        .limit(TOP_K)
    )
    kb_result = await db.execute(kb_query)
    kb_rows = kb_result.scalars().all()

    # 2. Search user history
    history_filters = [
        Embedding.user_id == user_id,
        Embedding.source_type.in_([SourceType.calendar_event, SourceType.daily_summary]),
    ]
    if pet_id:
        history_filters.append(Embedding.pet_id == pet_id)

    history_query = (
        select(Embedding)
        .where(and_(*history_filters))
        .order_by(Embedding.embedding.cosine_distance(query_embedding))
        .limit(TOP_K)
    )
    history_result = await db.execute(history_query)
    history_rows = history_result.scalars().all()

    # 3. Format results
    knowledge = []
    for row in kb_rows:
        meta = row.metadata_json or {}
        knowledge.append({
            "title": meta.get("title", ""),
            "content": row.content,
            "url": meta.get("url"),
        })

    history = []
    for row in history_rows:
        meta = row.metadata_json or {}
        history.append({
            "date": meta.get("date", ""),
            "content": row.content,
            "event_id": meta.get("event_id"),
        })

    return {"knowledge": knowledge, "history": history}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_rag_retrieval.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/retrieval.py backend/tests/test_rag_retrieval.py
git commit -m "feat: add vector retrieval for knowledge base and user history"
```

---

### Task 4: search_knowledge tool (definition + handler + validation)

**Files:**
- Create: `backend/app/agents/tools/knowledge.py`
- Modify: `backend/app/agents/tools/definitions.py`
- Modify: `backend/app/agents/tools/__init__.py`
- Modify: `backend/app/agents/validation.py`
- Modify: `backend/app/agents/locale.py`

- [ ] **Step 1: Add tool definition**

In `backend/app/agents/tools/definitions.py`, add to the end of `_BASE_TOOL_DEFINITIONS` list:

```python
{
    "type": "function",
    "function": {
        "name": "search_knowledge",
        "description": (
            "检索宠物健康知识库和用户历史记录，用于回答健康相关问题。\n"
            "【必须调用】用户描述宠物健康问题、症状、疾病、用药、饮食疑问时。\n"
            "如果用户发了图片（如呕吐物/皮肤/便便），从图片中观察到的症状特征作为 query。\n"
            "不要用于: 闲聊、创建日程、记录事件（用对应工具）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，描述症状或健康问题",
                },
                "pet_id": {
                    "type": "string",
                    "description": "相关宠物的 UUID，可选。明确知道是哪只宠物时传入",
                },
                "species": {
                    "type": "string",
                    "enum": ["dog", "cat"],
                    "description": "物种，用于过滤知识库",
                },
            },
            "required": ["query"],
        },
    },
},
```

- [ ] **Step 2: Implement handler**

Create `backend/app/agents/tools/knowledge.py`:

```python
"""search_knowledge tool — RAG retrieval for pet health Q&A."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.registry import register_tool
from app.rag.retrieval import retrieve_knowledge

logger = logging.getLogger(__name__)


@register_tool("search_knowledge", accepts_kwargs=True)
async def search_knowledge(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    **kwargs,
) -> dict:
    """Search knowledge base and user history for health-related queries."""
    query = arguments["query"]
    pet_id = arguments.get("pet_id")
    species = arguments.get("species")

    if pet_id:
        try:
            pet_id = uuid.UUID(pet_id)
        except ValueError:
            pet_id = None

    try:
        result = await retrieve_knowledge(
            query=query,
            db=db,
            user_id=user_id,
            pet_id=pet_id,
            species=species,
        )
    except Exception as exc:
        logger.error("search_knowledge_error", extra={"error": str(exc)[:200]})
        return {"success": False, "error": "知识库检索失败，请稍后再试"}

    has_results = bool(result["knowledge"] or result["history"])

    # Build references card if there are results with titles/urls
    card = None
    if has_results:
        items = []
        for k in result["knowledge"]:
            if k.get("title"):
                items.append({
                    "title": k["title"],
                    "url": k.get("url"),
                    "source": "knowledge",
                })
        for h in result["history"]:
            if h.get("content"):
                label = f"{h.get('date', '')} {h['content'][:30]}"
                items.append({
                    "title": label.strip(),
                    "event_id": h.get("event_id"),
                    "source": "history",
                })
        if items:
            card = {"type": "references", "items": items}

    response = {
        "success": True,
        "knowledge": result["knowledge"],
        "history": result["history"],
    }
    if card:
        response["card"] = card

    return response
```

- [ ] **Step 3: Register the module import**

In `backend/app/agents/tools/__init__.py`, add after the existing domain imports:

```python
import app.agents.tools.knowledge  # noqa: F401
```

And add to re-exports:

```python
from app.agents.tools.knowledge import search_knowledge
```

And add `"search_knowledge"` to the `__all__` list.

- [ ] **Step 4: Add validation**

In `backend/app/agents/validation.py`, add after the last `@_register` block:

```python
@_register("search_knowledge")
def _validate_search_knowledge(args: dict) -> list[str]:
    errors = _check_required(args, ["query"])
    errors += _check_uuid(args, "pet_id")
    if args.get("species") and args["species"] not in _SPECIES:
        errors.append(f"Invalid species: {args['species']!r} (expected dog/cat/other)")
    return errors
```

- [ ] **Step 5: Add to locale decision tree**

In `backend/app/agents/locale.py`, add to the `tool_decision_tree` zh string, after the existing rules:

```
- 用户描述宠物【健康问题/症状/疾病/用药/饮食疑问】→ 必须调用 search_knowledge
- 用户发了【宠物照片】问健康问题 → search_knowledge（用图片观察到的特征作为 query）
```

Add the same in English for the `en` version:

```
- User describes pet health issues/symptoms/illness/medication/diet questions → must call search_knowledge
- User sends pet photo asking about health → search_knowledge (use observed symptoms from image as query)
```

Add tool description translation key to `_STRINGS`:

```python
"tool_desc_search_knowledge": {
    "zh": "检索宠物健康知识库和用户历史记录，用于回答健康相关问题。",
    "en": "Search pet health knowledge base and user history to answer health-related questions.",
},
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/tools/knowledge.py backend/app/agents/tools/definitions.py \
       backend/app/agents/tools/__init__.py backend/app/agents/validation.py \
       backend/app/agents/locale.py
git commit -m "feat: add search_knowledge tool with definition, handler, and validation"
```

---

### Task 5: Async embedding generation in chat post-processing

**Files:**
- Create: `backend/app/rag/writer.py`
- Modify: `backend/app/routers/chat.py`
- Test: `backend/tests/test_rag_writer.py`

- [ ] **Step 1: Write failing test for write_chat_embedding**

Create `backend/tests/test_rag_writer.py`:

```python
"""Tests for RAG embedding writer."""

import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import date


@pytest.mark.asyncio
async def test_write_chat_embedding_stores_to_db():
    """write_chat_embedding should generate embedding and store in DB."""
    mock_embed = AsyncMock(return_value=[0.1] * 1536)
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    with patch("app.rag.writer.embed_text", mock_embed):
        from app.rag.writer import write_chat_embedding
        await write_chat_embedding(
            db=mock_db,
            user_id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            content="维尼今天呕吐了两次",
            pet_id=uuid.uuid4(),
        )

    mock_embed.assert_called_once_with("维尼今天呕吐了两次")
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()

    # Check the Embedding object
    added_obj = mock_db.add.call_args[0][0]
    assert added_obj.content == "维尼今天呕吐了两次"
    assert added_obj.embedding == [0.1] * 1536


@pytest.mark.asyncio
async def test_write_chat_embedding_handles_error_gracefully():
    """write_chat_embedding should log error and not raise on failure."""
    mock_embed = AsyncMock(side_effect=Exception("API error"))
    mock_db = AsyncMock()

    with patch("app.rag.writer.embed_text", mock_embed):
        from app.rag.writer import write_chat_embedding
        # Should not raise
        await write_chat_embedding(
            db=mock_db,
            user_id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            content="test",
        )

    mock_db.add.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_rag_writer.py -v
```

Expected: FAIL — module not found

- [ ] **Step 3: Implement write_chat_embedding**

Create `backend/app/rag/writer.py`:

```python
"""Async embedding writer — generates and stores embeddings after chat."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Embedding, SourceType
from app.rag.embeddings import embed_text

logger = logging.getLogger(__name__)


async def write_chat_embedding(
    db: AsyncSession,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    content: str,
    pet_id: uuid.UUID | None = None,
    source_type: SourceType = SourceType.daily_summary,
    metadata: dict | None = None,
) -> None:
    """Generate embedding for content and store in DB. Fails silently."""
    try:
        vector = await embed_text(content)
        emb = Embedding(
            user_id=user_id,
            pet_id=pet_id,
            source_type=source_type,
            source_id=source_id,
            content=content,
            embedding=vector,
            metadata_json=metadata,
        )
        db.add(emb)
        await db.commit()
        logger.info("embedding_written", extra={
            "source_type": source_type.value,
            "content_length": len(content),
        })
    except Exception as exc:
        logger.warning("embedding_write_error", extra={"error": str(exc)[:200]})
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_rag_writer.py -v
```

Expected: PASS

- [ ] **Step 5: Integrate into chat post-processing**

In `backend/app/routers/chat.py`, in Phase 4 (after the profile extractor save and before the assistant message save), add:

```python
    # --- RAG: 异步生成本轮对话的 embedding ---
    async def _write_embedding_bg():
        try:
            from app.rag.writer import write_chat_embedding
            from app.database import async_session as _async_session
            # Combine user message + assistant response as content
            emb_content = f"用户: {request.message}\n助手: {result.response_text[:500]}"
            async with _async_session() as bg_db:
                await write_chat_embedding(
                    db=bg_db,
                    user_id=user_id,
                    source_id=session.id,
                    content=emb_content,
                )
        except Exception as e:
            logger.warning("embedding_bg_error", extra={"error": str(e)[:200]})
    _track_task(_write_embedding_bg())
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/rag/writer.py backend/tests/test_rag_writer.py backend/app/routers/chat.py
git commit -m "feat: async embedding generation in chat post-processing"
```

---

### Task 6: Knowledge base ingestion CLI

**Files:**
- Create: `backend/app/rag/ingest.py`
- Create: `backend/knowledge/README.md`

- [ ] **Step 1: Implement ingest CLI**

Create `backend/app/rag/ingest.py`:

```python
"""CLI tool to ingest knowledge articles into the RAG knowledge base.

Usage:
    python -m app.rag.ingest --file knowledge/dog_vomiting.md --species dog --category 消化系统
    python -m app.rag.ingest --dir knowledge/ --species dog
    python -m app.rag.ingest --stats
"""

import argparse
import asyncio
import logging
import uuid
from pathlib import Path

from app.database import async_session
from app.models import Embedding, KnowledgeArticle, SourceType
from app.rag.embeddings import embed_text

logger = logging.getLogger(__name__)

# Chunk articles into ~400 char segments, keeping paragraph boundaries
CHUNK_SIZE = 400


def chunk_article(title: str, content: str) -> list[str]:
    """Split article into chunks, preserving paragraph boundaries."""
    paragraphs = content.split("\n\n")
    chunks = []
    current = f"# {title}\n\n"

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # If adding this paragraph would exceed chunk size, save current and start new
        if len(current) + len(para) > CHUNK_SIZE and len(current) > len(f"# {title}\n\n"):
            chunks.append(current.strip())
            current = f"# {title}\n\n{para}\n\n"
        else:
            current += para + "\n\n"

    if current.strip() and current.strip() != f"# {title}":
        chunks.append(current.strip())

    return chunks if chunks else [content]


def parse_markdown_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-like frontmatter from markdown. Returns (metadata, body)."""
    if not text.startswith("---"):
        # No frontmatter, try to extract title from first heading
        lines = text.strip().split("\n")
        title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("#") else "Untitled"
        return {"title": title}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    meta = {}
    for line in parts[1].strip().split("\n"):
        if ":" in line:
            key, val = line.split(":", 1)
            meta[key.strip()] = val.strip()
    return meta, parts[2].strip()


async def ingest_file(filepath: Path, species: str, category: str) -> int:
    """Ingest a single markdown file. Returns number of chunks created."""
    text = filepath.read_text(encoding="utf-8")
    meta, body = parse_markdown_frontmatter(text)

    title = meta.get("title", filepath.stem.replace("_", " ").replace("-", " "))
    url = meta.get("url")

    async with async_session() as db:
        # Create KnowledgeArticle
        article = KnowledgeArticle(
            title=title,
            content=body,
            category=category,
            species=species,
            url=url,
            metadata_json=meta,
        )
        db.add(article)
        await db.flush()  # Get article.id

        # Chunk and embed
        chunks = chunk_article(title, body)
        for chunk in chunks:
            vector = await embed_text(chunk)
            emb = Embedding(
                user_id=None,
                source_type=SourceType.knowledge_base,
                source_id=article.id,
                content=chunk,
                embedding=vector,
                metadata_json={
                    "title": title,
                    "url": url,
                    "species": species,
                    "category": category,
                },
            )
            db.add(emb)

        await db.commit()
        print(f"  ✓ {title}: {len(chunks)} chunks")
        return len(chunks)


async def show_stats():
    """Show knowledge base statistics."""
    from sqlalchemy import func, select
    async with async_session() as db:
        # Count articles
        article_count = (await db.execute(
            select(func.count()).select_from(KnowledgeArticle)
        )).scalar()

        # Count embeddings by source_type
        kb_count = (await db.execute(
            select(func.count()).select_from(Embedding).where(
                Embedding.source_type == SourceType.knowledge_base
            )
        )).scalar()

        user_count = (await db.execute(
            select(func.count()).select_from(Embedding).where(
                Embedding.source_type != SourceType.knowledge_base
            )
        )).scalar()

    print(f"Knowledge articles: {article_count}")
    print(f"Knowledge embeddings: {kb_count}")
    print(f"User history embeddings: {user_count}")


async def main():
    parser = argparse.ArgumentParser(description="Ingest knowledge into RAG")
    parser.add_argument("--file", type=Path, help="Single markdown file to ingest")
    parser.add_argument("--dir", type=Path, help="Directory of markdown files to ingest")
    parser.add_argument("--species", default="all", help="Species: dog/cat/all")
    parser.add_argument("--category", default="general", help="Category: 消化系统/皮肤/疫苗/...")
    parser.add_argument("--stats", action="store_true", help="Show knowledge base stats")
    args = parser.parse_args()

    if args.stats:
        await show_stats()
        return

    if args.file:
        count = await ingest_file(args.file, args.species, args.category)
        print(f"\nDone: {count} chunks ingested")
        return

    if args.dir:
        total = 0
        for f in sorted(args.dir.glob("*.md")):
            if f.name == "README.md":
                continue
            count = await ingest_file(f, args.species, args.category)
            total += count
        print(f"\nDone: {total} chunks ingested")
        return

    parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Create knowledge directory with README**

Create `backend/knowledge/README.md`:

```markdown
# Pet Health Knowledge Base

Place markdown files here for RAG ingestion.

## Format

Each file can optionally have YAML frontmatter:

    ---
    title: 犬呕吐常见原因与处理
    url: https://source-url.com/article
    ---

    ## 症状描述
    ...

    ## 问诊问题
    1. 呕吐物颜色？
    2. 频率？

    ## 判断逻辑
    - 黄色液体 + 单次 → ...

## Ingest

    cd backend
    python -m app.rag.ingest --file knowledge/dog_vomiting.md --species dog --category 消化系统
    python -m app.rag.ingest --dir knowledge/ --species dog
    python -m app.rag.ingest --stats
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/rag/ingest.py backend/knowledge/README.md
git commit -m "feat: add knowledge base ingestion CLI"
```

---

### Task 7: System prompt — add health Q&A guidance

**Files:**
- Modify: `backend/app/agents/prompts_v2.py`
- Modify: `backend/app/agents/locale.py`

- [ ] **Step 1: Add health Q&A prompt instructions to locale**

In `backend/app/agents/locale.py`, add to `_STRINGS`:

```python
"health_qa_guidance": {
    "zh": (
        "\n## 健康问答指引\n"
        "当用户描述宠物健康问题时：\n"
        "1. 必须先调用 search_knowledge 检索相关知识和历史\n"
        "2. 根据检索结果和用户已提供的信息判断：\n"
        "   - 关键信息已经足够 → 直接给建议，不要为了问而问\n"
        "   - 缺少关键信息 → 逐个询问（每次一个问题，提供选项方便快速回答）\n"
        "   - 用户说"跳过/直接告诉我/算了" → 根据已有信息立即给结论\n"
        "3. 如果用户发了图片，先从图片提取信息，减少需要问的问题\n"
        "4. 回答时自然融入知识，不要说"根据知识库"\n"
    ),
    "en": (
        "\n## Health Q&A Guidance\n"
        "When user describes pet health issues:\n"
        "1. Must call search_knowledge first to retrieve relevant knowledge and history\n"
        "2. Based on retrieved info and what user already provided:\n"
        "   - Enough info → give advice directly, don't ask unnecessary questions\n"
        "   - Missing key info → ask one question at a time with options\n"
        "   - User says 'skip/just tell me' → give conclusion with available info\n"
        "3. If user sent a photo, extract info from it first to reduce questions\n"
        "4. Naturally incorporate knowledge in your answer, don't say 'according to the knowledge base'\n"
    ),
},
```

- [ ] **Step 2: Add to system prompt builder**

In `backend/app/agents/prompts_v2.py`, in the `build_system_prompt` function, add the health QA guidance after the tool decision tree section:

```python
parts.append(t("health_qa_guidance", lang))
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/agents/prompts_v2.py backend/app/agents/locale.py
git commit -m "feat: add health Q&A guidance to system prompt"
```

---

### Task 8: iOS — References card + drawer

**Files:**
- Create: `ios-app/CozyPup/Views/Chat/ReferencesCard.swift`
- Modify: `ios-app/CozyPup/Views/Chat/ChatBubble.swift` (or wherever cards are rendered)
- Modify: `ios-app/CozyPup/Models/SSEEvent.swift` (or card model)

- [ ] **Step 1: Check existing card rendering structure**

Read these files to understand the current card rendering:
- The SSE card model — how cards are parsed from SSE events
- The ChatBubble/card rendering view — how existing cards (place, directions) are rendered
- Look for the pattern to add a new card type

- [ ] **Step 2: Add references card type to SSE model**

In the card type enum/switch (wherever cards are parsed), add `"references"` as a new card type. The data structure:

```swift
struct ReferenceItem: Codable, Identifiable {
    let title: String
    let url: String?
    let eventId: String?
    let source: String  // "knowledge" or "history"

    var id: String { title + (url ?? "") + (eventId ?? "") }

    enum CodingKeys: String, CodingKey {
        case title, url, source
        case eventId = "event_id"
    }
}
```

- [ ] **Step 3: Create ReferencesCard view**

Create `ios-app/CozyPup/Views/Chat/ReferencesCard.swift`:

The view should have:
1. A small button: "📎 References" styled with `Tokens.fontCaption`, `Tokens.textSecondary`, `Tokens.surface` background, `Tokens.radiusSmall` corner radius
2. On tap, presents a bottom sheet (`.sheet` with `presentationDetents([.medium])`)
3. Sheet content: list of reference items
   - Knowledge items: show title, tap opens URL via `SFSafariViewController` (use `Link` or `openURL`)
   - History items: show title with date prefix, tap navigates to calendar event

Use `Tokens.*` for all colors, fonts, spacing. Include `#Preview`.

- [ ] **Step 4: Integrate into chat bubble**

In the view that renders chat cards (after the AI message text), add a case for `"references"` type that renders the `ReferencesCard`.

- [ ] **Step 5: Test in simulator**

Build and run in Xcode. Send a health-related message and verify:
- References button appears after AI response
- Tapping opens drawer with reference list
- Links are clickable

- [ ] **Step 6: Commit**

```bash
cd ios-app
git add CozyPup/Views/Chat/ReferencesCard.swift CozyPup/Models/ CozyPup/Views/Chat/
git commit -m "feat: add References card with bottom drawer for health Q&A citations"
```

---

### Task 9: E2E test cases

**Files:**
- Modify: `backend/tests/e2e/TEST_PLAN.md`
- Modify: `backend/tests/e2e/test_messages.py`
- Modify: `backend/tests/e2e/run_audit.py`

- [ ] **Step 1: Add test cases to TEST_PLAN.md**

Add a new section to `backend/tests/e2e/TEST_PLAN.md`:

```markdown
## 8. Health Q&A (RAG)

### 8.1 Basic health query triggers search_knowledge
- Input: "维尼呕吐了怎么办"
- Expected: search_knowledge called with query containing "呕吐"
- Expected: AI response contains health advice (not "I don't know")

### 8.2 Health query with pet context
- Input: "维尼最近老是拉肚子"
- Expected: search_knowledge called with pet_id matching 维尼
- Expected: references card in response (if knowledge base has data)

### 8.3 Non-health query should NOT trigger search_knowledge
- Input: "帮我记录维尼今天吃了狗粮"
- Expected: create_calendar_event called, NOT search_knowledge

### 8.4 English health query
- Input: "My dog has been vomiting, what should I do?"
- Expected: search_knowledge called
```

- [ ] **Step 2: Add test messages**

In `backend/tests/e2e/test_messages.py`, add the health Q&A test messages following the existing pattern.

- [ ] **Step 3: Add to run_audit.py**

In `backend/tests/e2e/run_audit.py`, add the test cases to `build_test_cases()` following the existing pattern.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/e2e/
git commit -m "test: add E2E test cases for health Q&A RAG"
```

---

### Task 10: Config + environment setup

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add embedding model config**

In `backend/app/config.py`, add to the `Settings` class:

```python
embedding_model: str = "openai/text-embedding-3-small"
```

- [ ] **Step 2: Update embeddings.py to use config**

In `backend/app/rag/embeddings.py`, change the hardcoded model to use config:

```python
# Before
EMBEDDING_MODEL = "openai/text-embedding-3-small"

# After
from app.config import settings
# Use settings.embedding_model instead of hardcoded value
```

Update `embed_text` to use `settings.embedding_model`:

```python
async def embed_text(text: str) -> list[float]:
    """Generate a 1536-dim embedding for a single text string."""
    response = await litellm.aembedding(
        model=settings.embedding_model,
        input=[text],
        **llm_extra_kwargs(),
    )
    return response.data[0].embedding
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py backend/app/rag/embeddings.py
git commit -m "feat: add embedding_model to config settings"
```

---

### Task 11: Run full test suite + manual verification

- [ ] **Step 1: Run all existing tests**

```bash
cd backend && pytest tests/ -v --ignore=tests/e2e
```

Expected: All existing tests still pass (no regressions)

- [ ] **Step 2: Run RAG-specific tests**

```bash
cd backend && pytest tests/test_rag_embeddings.py tests/test_rag_retrieval.py tests/test_rag_writer.py -v
```

Expected: All RAG tests pass

- [ ] **Step 3: Manual smoke test**

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Test with curl:
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "维尼呕吐了怎么办"}' \
  --no-buffer
```

Verify:
- `search_knowledge` tool is called in the SSE stream
- AI gives a health-related response (even if knowledge base is empty, it should still respond normally)
- No errors in server logs

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A && git commit -m "fix: address issues found in testing"
```
