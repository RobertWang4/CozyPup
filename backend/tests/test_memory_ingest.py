import uuid

import pytest

from app.memory.ingest import chunk_article, parse_markdown_frontmatter


def test_parse_markdown_frontmatter_supports_lists():
    meta, body = parse_markdown_frontmatter(
        """---
title: Dog Vomiting
species: dog
aliases:
  - 呕吐
  - 吐了
---
Body text
"""
    )

    assert meta["title"] == "Dog Vomiting"
    assert meta["species"] == "dog"
    assert meta["aliases"] == ["呕吐", "吐了"]
    assert body == "Body text"


def test_chunk_article_prefixes_aliases_and_sections():
    chunks = chunk_article(
        "Dog Vomiting",
        "## Warning signs\nRepeated vomiting needs care.\n\n## Hydration\nWatch water intake.",
        aliases=["呕吐"],
    )

    assert chunks
    assert chunks[0].startswith("呕吐\n# Dog Vomiting")
    assert "## Warning signs" in chunks[0]


@pytest.mark.asyncio
async def test_ingest_replace_deletes_all_existing_article_chunks(monkeypatch, tmp_path):
    from app.memory import ingest

    old_source_ids = [uuid.uuid4() for _ in range(5)]
    deleted_source_ids = []

    class Result:
        def scalars(self):
            return self

        def all(self):
            return old_source_ids

    class FakeDb:
        async def execute(self, stmt):
            return Result()

    class FakeSession:
        async def __aenter__(self):
            return FakeDb()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_delete_memory_for_source(**kwargs):
        deleted_source_ids.append(kwargs["source_id"])

    async def fake_upsert_knowledge_memory(**kwargs):
        return None

    path = tmp_path / "dog_vomiting.md"
    path.write_text(
        """---
title: Dog Vomiting
species: dog
url: https://example.com/vomiting
---
Short updated content.
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(ingest, "async_session", lambda: FakeSession())
    monkeypatch.setattr(ingest, "delete_memory_for_source", fake_delete_memory_for_source)
    monkeypatch.setattr(ingest, "upsert_knowledge_memory", fake_upsert_knowledge_memory)

    await ingest.ingest_file(path, species="dog", category="digestive", replace=True)

    assert deleted_source_ids == old_source_ids
