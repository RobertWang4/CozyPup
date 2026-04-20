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


def chunk_article(
    title: str,
    content: str,
    aliases: list[str] | None = None,
) -> list[str]:
    """Split article into chunks. Each chunk starts with:

        [aliases line, if any]
        # {article title}
        ## {current section}     <-- tracked from ## headings in body

        <chunk paragraphs>

    Section header in the chunk prefix helps embedding retrieval target the
    right part of a multi-topic article (e.g., heatstroke vs seizure in an
    emergency doc). Aliases prepend Chinese synonyms so literal CJK queries
    hit the right chunks without fully cross-lingual embedding hops.
    """
    alias_line = ""
    if aliases:
        # Space-separated, no punctuation — maximizes BM25/token overlap.
        alias_line = " ".join(a.strip() for a in aliases if a and a.strip())
        if alias_line:
            alias_line = f"{alias_line}\n"

    def prefix(section: str | None) -> str:
        head = f"{alias_line}# {title}\n"
        if section:
            head += f"## {section}\n"
        return head + "\n"

    chunks: list[str] = []
    current_section: str | None = None
    current = prefix(current_section)

    def flush():
        nonlocal current
        body = current[len(prefix(current_section)):].strip()
        if body:
            chunks.append(current.strip())
        current = prefix(current_section)

    for raw in content.split("\n\n"):
        para = raw.strip()
        if not para:
            continue

        # New section? The paragraph may be "## Title\n<body...>" because
        # bullet lists often share a paragraph block with their heading.
        if para.startswith("## "):
            header, _, rest = para.partition("\n")
            flush()
            current_section = header[3:].strip()
            current = prefix(current_section)
            para = rest.strip()
            if not para:
                continue

        # Skip the main-title line if it appears on its own line.
        elif para.startswith("# "):
            continue

        # Size check: if adding this paragraph would blow the budget AND
        # the current chunk already has some body, flush first.
        if len(current) + len(para) > CHUNK_SIZE and current.strip() != prefix(current_section).strip():
            flush()

        current += para + "\n\n"

    flush()
    return chunks if chunks else [content]


def _coerce(val: str):
    v = val.strip()
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no"):
        return False
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    return v


def parse_markdown_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-like frontmatter. Supports scalars, booleans, and simple `- item` lists."""
    if not text.startswith("---"):
        lines = text.strip().split("\n")
        title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("#") else "Untitled"
        return {"title": title}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    meta: dict = {}
    current_key: str | None = None
    for raw in parts[1].splitlines():
        if not raw.strip():
            continue
        # list continuation: "  - item"
        stripped = raw.lstrip()
        if stripped.startswith("- ") and current_key:
            meta.setdefault(current_key, [])
            if isinstance(meta[current_key], list):
                meta[current_key].append(_coerce(stripped[2:]))
            continue
        if ":" in raw and not raw.startswith(" "):
            key, _, val = raw.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "":
                current_key = key
                meta[key] = []
            else:
                meta[key] = _coerce(val)
                current_key = None
    return meta, parts[2].strip()


async def _delete_existing(db, title: str) -> int:
    """Delete KnowledgeArticle(s) with the given title plus their embeddings. Returns count."""
    from sqlalchemy import delete, select
    ids = (await db.execute(
        select(KnowledgeArticle.id).where(KnowledgeArticle.title == title)
    )).scalars().all()
    if not ids:
        return 0
    await db.execute(
        delete(Embedding).where(
            Embedding.source_type == SourceType.knowledge_base,
            Embedding.source_id.in_(ids),
        )
    )
    await db.execute(delete(KnowledgeArticle).where(KnowledgeArticle.id.in_(ids)))
    return len(ids)


async def ingest_file(
    filepath: Path,
    species: str,
    category: str,
    replace: bool = False,
) -> int:
    """Ingest a single markdown file. Frontmatter values override CLI defaults.

    If replace=True, existing articles with the same title (and their embeddings) are deleted first.
    """
    text = filepath.read_text(encoding="utf-8")
    meta, body = parse_markdown_frontmatter(text)

    title = meta.get("title", filepath.stem.replace("_", " ").replace("-", " "))
    url = meta.get("url")
    species_final = meta.get("species") or species
    category_final = meta.get("category") or category
    severity_final = meta.get("severity")
    aliases_raw = meta.get("aliases") or []
    aliases = aliases_raw if isinstance(aliases_raw, list) else [aliases_raw]

    async with async_session() as db:
        if replace:
            n = await _delete_existing(db, title)
            if n:
                print(f"  ↺ replaced {n} existing article(s) titled {title!r}")

        article = KnowledgeArticle(
            title=title,
            content=body,
            category=category_final,
            species=species_final,
            url=url,
            metadata_json=meta,
        )
        db.add(article)
        await db.flush()

        chunks = chunk_article(title, body, aliases=aliases)
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
                    "species": species_final,
                    "category": category_final,
                    "severity": severity_final,
                    "aliases": aliases,
                },
            )
            db.add(emb)

        await db.commit()
        print(
            f"  ✓ {title}: {len(chunks)} chunks "
            f"(species={species_final}, category={category_final}, severity={severity_final}, aliases={len(aliases)})"
        )
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
    parser.add_argument(
        "--replace",
        action="store_true",
        help="If an article with the same title already exists, delete it (and its embeddings) before re-inserting.",
    )
    args = parser.parse_args()

    if args.stats:
        await show_stats()
        return

    if args.file:
        count = await ingest_file(args.file, args.species, args.category, replace=args.replace)
        print(f"\nDone: {count} chunks ingested")
        return

    if args.dir:
        total = 0
        for f in sorted(args.dir.glob("*.md")):
            if f.name == "README.md":
                continue
            count = await ingest_file(f, args.species, args.category, replace=args.replace)
            total += count
        print(f"\nDone: {total} chunks ingested")
        return

    parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
