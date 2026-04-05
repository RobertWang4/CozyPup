"""Miscellaneous tool handlers: places, email, language, emergency."""

import asyncio
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

    # Build enriched place list
    places_for_card = [
        {
            "place_id": p.get("place_id", ""),
            "name": p["name"],
            "address": p["address"],
            "rating": p.get("rating"),
            "is_open": p.get("open_now"),
            "lat": p["lat"],
            "lng": p["lng"],
            "distance": None,
            "duration": None,
        }
        for p in places
    ]

    # Enrich top 5 with distance/duration
    top_n = min(5, len(places_for_card))
    direction_tasks = [
        places_service.get_directions(
            origin_lat=location["lat"],
            origin_lng=location["lng"],
            dest_lat=p["lat"],
            dest_lng=p["lng"],
        )
        for p in places_for_card[:top_n]
    ]
    directions = await asyncio.gather(*direction_tasks, return_exceptions=True)
    for i, d in enumerate(directions):
        if isinstance(d, dict):
            places_for_card[i]["distance"] = d.get("distance")
            places_for_card[i]["duration"] = d.get("duration")

    card = {
        "type": "place_card",
        "query": query,
        "places": places_for_card,
    }

    # Text summary for LLM
    top_results = []
    for p in places_for_card[:5]:
        parts = [f"{p['name']} — {p['address']}"]
        if p.get("distance"):
            parts.append(f"({p['distance']}, {p['duration']})")
        if p.get("rating"):
            parts.append(f"⭐{p['rating']}")
        top_results.append(" ".join(parts))

    return {
        "success": True,
        "places_count": len(places_for_card),
        "top_results": top_results,
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


@register_tool("sync_calendar")
async def sync_calendar(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Trigger Apple Calendar sync on the client."""
    return {
        "success": True,
        "card": {
            "type": "calendar_sync",
        },
    }


@register_tool("search_places_text")
async def search_places_text(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    **_kwargs,
) -> dict:
    """Search for a place by text query (address or name)."""
    query = arguments.get("query", "")
    if not query:
        return {"success": False, "error": "No query provided."}

    from app.services.places import places_service
    places = await places_service.search_text(query=query)

    if not places:
        return {
            "success": True,
            "places": [],
            "message": f"No results found for '{query}'.",
        }

    return {
        "success": True,
        "places": places,
        "places_count": len(places),
    }


@register_tool("get_place_details")
async def get_place_details_tool(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    **_kwargs,
) -> dict:
    """Get detailed info for a single place."""
    from app.services.places import places_service

    place_id = arguments["place_id"]
    detail = await places_service.get_place_details(place_id)
    if not detail:
        return {"success": False, "error": f"No details found for place_id: {place_id}"}

    return {
        "success": True,
        "card": {
            "type": "place_detail",
            "name": detail["name"],
            "address": detail["address"],
            "rating": detail.get("rating"),
            "phone": detail.get("phone"),
            "reviews": detail.get("reviews", [])[:3],
            "is_open": detail.get("is_open"),
            "opening_hours": detail.get("opening_hours", []),
            "website": detail.get("website"),
            "google_maps_url": detail.get("google_maps_url"),
        },
        "detail": detail,
    }


@register_tool("get_directions", accepts_kwargs=True)
async def get_directions_tool(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    location: dict | None = None,
    **_kwargs,
) -> dict:
    """Get directions from user's location to a destination."""
    if not location or "lat" not in location or "lng" not in location:
        return {
            "success": False,
            "error": "No location available. Ask the user to share their location.",
        }

    from app.services.places import places_service

    dest_lat = arguments["dest_lat"]
    dest_lng = arguments["dest_lng"]
    dest_name = arguments.get("dest_name", "")
    mode = arguments.get("mode", "driving")

    result = await places_service.get_directions(
        origin_lat=location["lat"],
        origin_lng=location["lng"],
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        mode=mode,
    )

    if not result:
        return {"success": False, "error": "No route found."}

    return {
        "success": True,
        "card": {
            "type": "directions",
            "dest_name": dest_name,
            "dest_lat": dest_lat,
            "dest_lng": dest_lng,
            "distance": result["distance"],
            "duration": result["duration"],
            "mode": mode,
        },
        "distance": result["distance"],
        "duration": result["duration"],
        "mode": mode,
    }
