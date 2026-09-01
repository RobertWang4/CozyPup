"""CLI tool to ingest trusted articles into MemWeaver knowledge memory.

Usage:
    python -m app.memory.ingest --file knowledge/dog_vomiting.md --species dog --category digestive
    python -m app.memory.ingest --dir knowledge/ --species dog
    python -m app.memory.ingest --stats
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from pathlib import Path

from sqlalchemy import func, select

from app.database import async_session
from app.memory.store import delete_memory_for_source, upsert_knowledge_memory
from app.models import MemoryNode, MemoryNodeType

CHUNK_SIZE = 400


def chunk_article(
    title: str,
    content: str,
    aliases: list[str] | None = None,
) -> list[str]:
    alias_line = ""
    if aliases:
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

    def flush() -> None:
        nonlocal current
        body = current[len(prefix(current_section)):].strip()
        if body:
            chunks.append(current.strip())
        current = prefix(current_section)

    for raw in content.split("\n\n"):
        para = raw.strip()
        if not para:
            continue
        if para.startswith("## "):
            header, _, rest = para.partition("\n")
            flush()
            current_section = header[3:].strip()
            current = prefix(current_section)
            para = rest.strip()
            if not para:
                continue
        elif para.startswith("# "):
            continue

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


def _article_source_id(title: str, species: str, url: str | None, chunk_index: int) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"memweaver:{title}|{species}|{url or ''}|{chunk_index}")


async def _existing_article_source_ids(
    db,
    *,
    title: str,
    species: str,
    url: str | None,
) -> list[uuid.UUID]:
    filters = [
        MemoryNode.node_type == MemoryNodeType.knowledge,
        MemoryNode.source_kind == "knowledge_article",
        MemoryNode.title == title,
        MemoryNode.metadata_json["species"].as_string() == species,
    ]
    url_col = MemoryNode.metadata_json["url"].as_string()
    filters.append(url_col == url if url else url_col.is_(None))

    rows = (await db.execute(select(MemoryNode.source_id).where(*filters))).scalars().all()
    return list(dict.fromkeys(rows))


async def ingest_file(
    filepath: Path,
    *,
    species: str,
    category: str,
    replace: bool = False,
) -> int:
    text = filepath.read_text(encoding="utf-8")
    meta, body = parse_markdown_frontmatter(text)

    title = meta.get("title", filepath.stem.replace("_", " ").replace("-", " "))
    url = meta.get("url")
    species_final = meta.get("species") or species
    category_final = meta.get("category") or category
    aliases_raw = meta.get("aliases") or []
    aliases = aliases_raw if isinstance(aliases_raw, list) else [aliases_raw]
    chunks = chunk_article(title, body, aliases=aliases)

    async with async_session() as db:
        if replace:
            for source_id in await _existing_article_source_ids(
                db,
                title=title,
                species=species_final,
                url=url,
            ):
                await delete_memory_for_source(
                    db=db,
                    source_kind="knowledge_article",
                    source_id=source_id,
                    node_type=MemoryNodeType.knowledge,
                )

        for idx, chunk in enumerate(chunks):
            await upsert_knowledge_memory(
                db=db,
                title=title,
                content=chunk,
                species=species_final,
                category=category_final,
                url=url,
                source_id=_article_source_id(title, species_final, url, idx),
                metadata={
                    "chunk_index": idx,
                    "chunk_count": len(chunks),
                    "aliases": aliases,
                    "source_file": str(filepath),
                },
            )
    return len(chunks)


async def print_stats() -> None:
    async with async_session() as db:
        rows = (await db.execute(
            select(MemoryNode.node_type, func.count()).group_by(MemoryNode.node_type)
        )).all()
    counts = {node_type.value if hasattr(node_type, "value") else str(node_type): count for node_type, count in rows}
    print(f"Knowledge memory nodes:  {counts.get('knowledge', 0)}")
    print(f"Behavioral memory nodes: {counts.get('behavioral', 0)}")
    print(f"Cognitive memory nodes:  {counts.get('cognitive', 0)}")


async def _run(args) -> None:
    if args.stats:
        await print_stats()
        return

    paths: list[Path] = []
    if args.file:
        paths.append(Path(args.file))
    if args.dir:
        paths.extend(sorted(Path(args.dir).glob("*.md")))
    if not paths:
        raise SystemExit("Provide --file, --dir, or --stats")

    total = 0
    for path in paths:
        count = await ingest_file(
            path,
            species=args.species,
            category=args.category,
            replace=args.replace,
        )
        total += count
        print(f"ingested {path}: {count} memory node(s)")
    print(f"done: {len(paths)} file(s), {total} memory node(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest trusted articles into MemWeaver memory")
    parser.add_argument("--file")
    parser.add_argument("--dir")
    parser.add_argument("--species", default="all")
    parser.add_argument("--category", default="general")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
