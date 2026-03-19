"""Google Places Nearby Search service with in-memory TTL cache."""

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PLACES_API_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
CACHE_TTL_SECONDS = 2 * 60 * 60  # 2 hours
MAX_RESULTS = 10


class PlacesService:
    """Searches Google Places Nearby Search API with caching."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._cache: dict[str, tuple[float, list[dict]]] = {}

    def _cache_key(self, lat: float, lng: float, query: str) -> str:
        return f"{lat:.3f},{lng:.3f},{query}"

    def _get_cached(self, key: str) -> list[dict] | None:
        if key in self._cache:
            ts, results = self._cache[key]
            if time.monotonic() - ts < CACHE_TTL_SECONDS:
                return results
            del self._cache[key]
        return None

    def _set_cached(self, key: str, results: list[dict]) -> None:
        self._cache[key] = (time.monotonic(), results)

    async def search_nearby(
        self,
        lat: float,
        lng: float,
        query: str,
        radius: int = 5000,
    ) -> list[dict]:
        """Search for nearby places. Returns up to 10 results.

        Returns empty list if API key is missing or request fails.
        """
        if not self.api_key:
            logger.warning("places_no_api_key", extra={"query": query})
            return []

        cache_key = self._cache_key(lat, lng, query)
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug("places_cache_hit", extra={"cache_key": cache_key})
            return cached

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    PLACES_API_URL,
                    params={
                        "location": f"{lat},{lng}",
                        "radius": radius,
                        "keyword": query,
                        "key": self.api_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error(
                "places_api_error",
                extra={"error_type": type(exc).__name__, "error_message": str(exc)[:200], "query": query},
            )
            return []

        results = []
        for place in data.get("results", [])[:MAX_RESULTS]:
            location = place.get("geometry", {}).get("location", {})
            results.append(
                {
                    "name": place.get("name", ""),
                    "address": place.get("vicinity", ""),
                    "rating": place.get("rating"),
                    "place_id": place.get("place_id", ""),
                    "lat": location.get("lat", 0.0),
                    "lng": location.get("lng", 0.0),
                    "open_now": place.get("opening_hours", {}).get("open_now")
                    if place.get("opening_hours")
                    else None,
                }
            )

        self._set_cached(cache_key, results)
        logger.info("places_search", extra={"query": query, "result_count": len(results)})
        return results


places_service = PlacesService(api_key=settings.google_places_api_key)
