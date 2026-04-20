"""search_knowledge tool — RAG retrieval for pet health Q&A.

Delegates to `app.rag.retrieval.retrieve_knowledge`, which queries both
the global KnowledgeArticle embeddings and the user's per-pet history.
Builds a `references` card when any results have titles/urls so the iOS
client can surface a "Sources" drawer.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.registry import register_tool
from app.models import Pet
from app.rag.retrieval import retrieve_knowledge

logger = logging.getLogger(__name__)


async def _resolve_species(
    db: AsyncSession,
    user_id: uuid.UUID,
    pet_id: uuid.UUID | None,
) -> str | None:
    """Derive species from the named pet, or from the user's single pet.

    Ensures the RAG filter never runs unbounded when the LLM forgets to pass
    species. If the user has exactly one pet, we can safely default to it.
    """
    if pet_id:
        pet = await db.get(Pet, pet_id)
        if pet and pet.user_id == user_id:
            val = pet.species
            return val.value if hasattr(val, "value") else str(val)
    rows = (await db.execute(select(Pet).where(Pet.user_id == user_id))).scalars().all()
    if len(rows) == 1:
        val = rows[0].species
        return val.value if hasattr(val, "value") else str(val)
    return None


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

    if not species:
        species = await _resolve_species(db, user_id, pet_id)

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
