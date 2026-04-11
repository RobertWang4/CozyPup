"""CLI tool to ingest knowledge articles into the RAG knowledge base.

Usage:
    python -m app.rag.ingest --file knowledge/dog_vomiting.md --species dog --category 消化系统
    python -m app.rag.ingest --dir knowledge/ --species dog
    python -m app.rag.ingest --stats
"""

import argparse
import asyncio
import logging
from pathlib import Path

from app.database import async_session
from app.models import Embedding, KnowledgeArticle, SourceType
from app.rag.embeddings import embed_text

logger = logging.getLogger(__name__)

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
        article = KnowledgeArticle(
            title=title,
            content=body,
            category=category,
            species=species,
            url=url,
            metadata_json=meta,
        )
        db.add(article)
        await db.flush()

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
        article_count = (await db.execute(
            select(func.count()).select_from(KnowledgeArticle)
        )).scalar()

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
