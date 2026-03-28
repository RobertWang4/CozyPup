import logging

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_user_id
from app.services.places import places_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/places", tags=["places"])


@router.get("/nearby")
async def search_nearby(
    lat: float = Query(...),
    lng: float = Query(...),
    query: str = Query(default=""),
    radius: int = Query(default=1000),
    _user_id=Depends(get_current_user_id),
):
    """Search nearby places by GPS coordinates."""
    results = await places_service.search_nearby(lat=lat, lng=lng, query=query, radius=radius)
    return {"places": results}


@router.get("/search")
async def search_text(
    query: str = Query(...),
    _user_id=Depends(get_current_user_id),
):
    """Search places by text query (address or name)."""
    results = await places_service.search_text(query=query)
    return {"places": results}
