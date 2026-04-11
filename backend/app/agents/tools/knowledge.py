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
