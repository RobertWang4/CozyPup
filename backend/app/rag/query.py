"""Ad-hoc RAG query CLI — inspect retrieval results outside the chat loop.

Lets you dry-run queries against the knowledge base + history embeddings
without going through the agent. Mostly useful for:
  - tuning `settings.rag_distance_threshold`
  - verifying that newly ingested articles actually get recalled
  - spot-checking per-user history retrieval after backfill

Usage:
    python -m app.rag.query "狗呕吐"
    python -m app.rag.query "vomiting" --species dog
    python -m app.rag.query "维尼上次拉肚子" --user alice@example.com
    python -m app.rag.query "..." --user alice@example.com --pet-id <uuid>
    python -m app.rag.query --stats
"""

import argparse
import asyncio
import uuid

from sqlalchemy import func, select

from app.database import async_session
from app.models import Embedding, KnowledgeArticle, SourceType, User
from app.rag.retrieval import retrieve_knowledge


async def _resolve_user(db, email: str) -> uuid.UUID | None:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        print(f"user not found: {email}")
        return None
    return user.id


async def run_query(
    query: str,
    user_email: str | None,
    pet_id: str | None,
    species: str | None,
) -> None:
    async with async_session() as db:
        if user_email:
            user_id = await _resolve_user(db, user_email)
            if user_id is None:
                return
        else:
            # Anonymous query — pass a sentinel UUID so history filter matches nothing.
            user_id = uuid.UUID(int=0)

        pid = uuid.UUID(pet_id) if pet_id else None
        result = await retrieve_knowledge(
            query=query, db=db, user_id=user_id, pet_id=pid, species=species,
        )

    print(f"\nQuery: {query!r}")
    print(f"  user={user_email or '(anon)'}  pet_id={pet_id or '-'}  species={species or '-'}")

    kb = result["knowledge"]
    hist = result["history"]
    print(f"\nKnowledge ({len(kb)}):")
    if not kb:
        print("  (no results above threshold)")
    for i, k in enumerate(kb, 1):
        dist = k.get("distance")
        ds = f"{dist:.3f}" if dist is not None else "?"
        title = k.get("title") or "(untitled)"
        url = k.get("url") or ""
        preview = k["content"].replace("\n", " ")[:120]
        print(f"  {i}. [{ds}] {title}  {url}")
        print(f"       {preview}…")

    print(f"\nHistory ({len(hist)}):")
    if not hist:
        print("  (no results)")
    for i, h in enumerate(hist, 1):
        dist = h.get("distance")
        ds = f"{dist:.3f}" if dist is not None else "?"
        preview = h["content"].replace("\n", " ")[:120]
        print(f"  {i}. [{ds}] {h.get('date', '')}  event={h.get('event_id', '-')}")
        print(f"       {preview}…")


async def show_stats() -> None:
    """Counts — complements `python -m app.rag.ingest --stats` with per-source-type breakdown."""
    async with async_session() as db:
        article_count = (await db.execute(
            select(func.count()).select_from(KnowledgeArticle)
        )).scalar()

        kb = (await db.execute(
            select(func.count()).select_from(Embedding).where(
                Embedding.source_type == SourceType.knowledge_base
            )
        )).scalar()
        events = (await db.execute(
            select(func.count()).select_from(Embedding).where(
                Embedding.source_type == SourceType.calendar_event
            )
        )).scalar()
        summaries = (await db.execute(
            select(func.count()).select_from(Embedding).where(
                Embedding.source_type == SourceType.daily_summary
            )
        )).scalar()

    print(f"KnowledgeArticle rows:        {article_count}")
    print(f"Embedding (knowledge_base):   {kb}")
    print(f"Embedding (calendar_event):   {events}")
    print(f"Embedding (daily_summary):    {summaries}")


async def main() -> None:
    p = argparse.ArgumentParser(description="Ad-hoc RAG retrieval CLI")
    p.add_argument("query", nargs="?", help="Query text")
    p.add_argument("--user", help="User email (enables history retrieval)")
    p.add_argument("--pet-id", help="Restrict history to this pet UUID")
    p.add_argument("--species", help="dog/cat/all (for KB filter)")
    p.add_argument("--stats", action="store_true", help="Show row counts per embedding source type")
    args = p.parse_args()

    if args.stats:
        await show_stats()
        return
    if not args.query:
        p.print_help()
        return
    await run_query(args.query, args.user, args.pet_id, args.species)


if __name__ == "__main__":
    asyncio.run(main())
