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

    async def search_nearby_general(self, lat: float, lng: float, radius: int = 1000) -> list[dict]:
        """Get general nearby places without keyword using Text Search with location bias."""
        if not self.api_key:
            return []

        cache_key = self._cache_key(lat, lng, "_general")
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                    params={
                        "location": f"{lat},{lng}",
                        "radius": radius,
                        "key": self.api_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error("places_nearby_general_error", extra={"error": str(exc)[:200]})
            return []

        results = []
        for place in data.get("results", [])[:MAX_RESULTS]:
            location = place.get("geometry", {}).get("location", {})
            results.append({
                "name": place.get("name", ""),
                "address": place.get("vicinity", ""),
                "place_id": place.get("place_id", ""),
                "lat": location.get("lat", 0.0),
                "lng": location.get("lng", 0.0),
                "rating": place.get("rating"),
            })

        self._set_cached(cache_key, results)
        logger.info("places_nearby_general", extra={"result_count": len(results)})
        return results

    async def search_text(self, query: str) -> list[dict]:
        """Search places by text query (address, name). Returns up to 5 results."""
        if not self.api_key:
            logger.warning("places_no_api_key", extra={"query": query})
            return []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://maps.googleapis.com/maps/api/place/textsearch/json",
                    params={"query": query, "key": self.api_key},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error("places_text_search_error", extra={
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:200],
                "query": query,
            })
            return []

        results = []
        for place in data.get("results", [])[:5]:
            location = place.get("geometry", {}).get("location", {})
            results.append({
                "name": place.get("name", ""),
                "address": place.get("formatted_address", ""),
                "place_id": place.get("place_id", ""),
                "lat": location.get("lat", 0.0),
                "lng": location.get("lng", 0.0),
            })

        logger.info("places_text_search", extra={"query": query, "result_count": len(results)})
        return results

    async def get_place_details(self, place_id: str) -> dict | None:
        """Fetch detailed info for a single place."""
        cache_key = f"detail:{place_id}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached[0] if cached else None

        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            "place_id": place_id,
            "fields": "name,formatted_address,formatted_phone_number,rating,reviews,opening_hours,website,url,user_ratings_total,geometry",
            "key": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error("places_detail_error", extra={
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:200],
                "place_id": place_id,
            })
            return None

        r = data.get("result")
        if not r:
            return None

        result = {
            "name": r.get("name", ""),
            "address": r.get("formatted_address", ""),
            "phone": r.get("formatted_phone_number"),
            "rating": r.get("rating"),
            "review_count": r.get("user_ratings_total", 0),
            "reviews": [
                {
                    "author": rev.get("author_name", ""),
                    "rating": rev.get("rating", 0),
                    "text": rev.get("text", ""),
                    "time": rev.get("relative_time_description", ""),
                }
                for rev in (r.get("reviews") or [])[:3]
            ],
            "opening_hours": [
                line for line in (r.get("opening_hours", {}).get("weekday_text") or [])
            ],
            "is_open": (r.get("opening_hours") or {}).get("open_now"),
            "website": r.get("website"),
            "google_maps_url": r.get("url"),
            "lat": r.get("geometry", {}).get("location", {}).get("lat"),
            "lng": r.get("geometry", {}).get("location", {}).get("lng"),
        }

        self._set_cached(cache_key, [result])
        return result

    async def get_directions(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        mode: str = "driving",
    ) -> dict | None:
        """Get route summary between two points."""
        url = "https://maps.googleapis.com/maps/api/directions/json"
        params = {
            "origin": f"{origin_lat},{origin_lng}",
            "destination": f"{dest_lat},{dest_lng}",
            "mode": mode,
            "key": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error("places_directions_error", extra={
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:200],
            })
            return None

        routes = data.get("routes", [])
        if not routes:
            return None

        leg = routes[0]["legs"][0]
        return {
            "distance": leg["distance"]["text"],
            "duration": leg["duration"]["text"],
            "mode": mode,
        }


places_service = PlacesService(api_key=settings.google_places_api_key)
