"""Miscellaneous tool handlers: places, email, language, emergency."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.registry import register_tool


@register_tool("search_places", accepts_kwargs=True)
async def search_places(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    location: dict | None = None,
    **_kwargs,
) -> dict:
    """Search for nearby places via Google Places API."""
    if not location or "lat" not in location or "lng" not in location:
        return {
            "success": False,
            "error": "No location available. Ask the user to share their location.",
        }

    from app.services.places import places_service  # lazy import

    query = arguments["query"]
    places = await places_service.search_nearby(
        lat=location["lat"], lng=location["lng"], query=query
    )

    if not places:
        return {
            "success": True,
            "places": [],
            "message": f"No results found for '{query}' nearby.",
        }

    card = {
        "type": "map",
        "query": query,
        "places": [
            {
                "name": p["name"],
                "address": p["address"],
                "rating": p.get("rating"),
                "lat": p["lat"],
                "lng": p["lng"],
            }
            for p in places
        ],
    }

    return {
        "success": True,
        "places_count": len(places),
        "top_results": [f"{p['name']} — {p['address']}" for p in places[:5]],
        "card": card,
    }


@register_tool("draft_email")
async def draft_email(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Wrap an email draft into a card for the frontend."""
    subject = arguments["subject"]
    body = arguments["body"]

    card = {
        "type": "email",
        "subject": subject,
        "body": body,
    }

    return {
        "success": True,
        "card": card,
    }


@register_tool("set_language")
async def set_language(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Change the app display language (frontend-only action)."""
    language = arguments["language"]

    card = {
        "type": "set_language",
        "language": language,
    }

    return {
        "success": True,
        "language": language,
        "card": card,
    }


@register_tool("trigger_emergency")
async def trigger_emergency(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Return an emergency card for the frontend to display."""
    return {
        "success": True,
        "card": {
            "type": "emergency",
            "message": arguments["message"],
            "action": arguments["action"],
        },
    }
