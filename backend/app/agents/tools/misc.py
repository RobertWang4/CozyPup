"""Miscellaneous tool handlers — places, email, language, emergency, product.

Most of these are thin wrappers that emit a card for the iOS client to
render (email drafts, emergency banners, language-switch signals). The
places handlers call out to the Google Places service and enrich the
top N results with distance/duration so the LLM can answer "how far"
questions without a follow-up round.
"""

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

    # Text summary for LLM (include place_id so LLM can call get_place_details later)
    top_results = []
    for i, p in enumerate(places_for_card[:5]):
        parts = [f"{i+1}. {p['name']}"]
        if p.get("rating"):
            parts.append(f"⭐{p['rating']}")
        if p.get("distance"):
            parts.append(f"{p['distance']}")
        parts.append(f"[place_id={p['place_id']}]")
        parts.append(f"[lat={p['lat']}, lng={p['lng']}]")
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


@register_tool("introduce_product")
async def introduce_product(arguments: dict, **_kwargs) -> dict:
    """Return product capabilities for the LLM to introduce to the user."""
    return {
        "success": True,
        "capabilities": {
            "record": "记录宠物日常（饮食、散步、洗澡、异常症状等）到日历",
            "medical": "记录医疗事件（疫苗、驱虫、体检）+ 设置提醒",
            "find_places": "搜索附近宠物医院、宠物店、狗公园，查看评价和导航",
            "reminders": "设置定时提醒（喂药、打疫苗、体检等）",
            "pet_profile": "管理宠物档案（体重、生日、品种、过敏信息等）",
            "spending": "记录宠物消费，查看统计",
            "emergency": "紧急情况快速响应（中毒、抽搐等）",
            "email": "生成兽医沟通邮件",
        },
        "hint": "用自然语言向用户介绍以上功能，语气友好，举几个具体例子让用户知道怎么用。不要列出所有功能的清单，而是像朋友一样自然地介绍。",
    }
