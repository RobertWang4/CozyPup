"""Tests for the Map Agent and PlacesService."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.agents.map_agent import MapAgent
from app.services.places import PlacesService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_PLACES_API_RESPONSE = {
    "results": [
        {
            "name": "Happy Paws Vet",
            "vicinity": "123 Main St",
            "rating": 4.5,
            "place_id": "abc123",
            "geometry": {"location": {"lat": 37.7749, "lng": -122.4194}},
            "opening_hours": {"open_now": True},
        },
        {
            "name": "Pet Care Clinic",
            "vicinity": "456 Oak Ave",
            "rating": 4.0,
            "place_id": "def456",
            "geometry": {"location": {"lat": 37.7750, "lng": -122.4180}},
        },
    ],
    "status": "OK",
}


def _make_litellm_response(content: str):
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# PlacesService tests
# ---------------------------------------------------------------------------


class TestPlacesService:
    """Test Google Places service with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_search_nearby_returns_formatted_results(self):
        service = PlacesService(api_key="test-key")
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_PLACES_API_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.places.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await service.search_nearby(37.7749, -122.4194, "vet")

        assert len(results) == 2
        assert results[0]["name"] == "Happy Paws Vet"
        assert results[0]["address"] == "123 Main St"
        assert results[0]["rating"] == 4.5
        assert results[0]["place_id"] == "abc123"
        assert results[0]["lat"] == 37.7749
        assert results[0]["lng"] == -122.4194
        assert results[0]["open_now"] is True
        assert results[1]["open_now"] is None  # No opening_hours

    @pytest.mark.asyncio
    async def test_search_nearby_passes_correct_params(self):
        service = PlacesService(api_key="my-api-key")
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.places.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await service.search_nearby(40.0, -74.0, "dog park", radius=3000)

        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs["params"]
        assert params["location"] == "40.0,-74.0"
        assert params["radius"] == 3000
        assert params["keyword"] == "dog park"
        assert params["key"] == "my-api-key"

    @pytest.mark.asyncio
    async def test_cache_hit_does_not_call_api_again(self):
        service = PlacesService(api_key="test-key")
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_PLACES_API_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.places.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # First call — hits API
            results1 = await service.search_nearby(37.775, -122.419, "vet")
            assert mock_client.get.call_count == 1

            # Second call with same (rounded) coords — should use cache
            results2 = await service.search_nearby(37.775, -122.419, "vet")
            assert mock_client.get.call_count == 1  # No new API call

        assert results1 == results2

    @pytest.mark.asyncio
    async def test_different_query_calls_api_again(self):
        service = PlacesService(api_key="test-key")
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_PLACES_API_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.places.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await service.search_nearby(37.775, -122.419, "vet")
            assert mock_client.get.call_count == 1

            await service.search_nearby(37.775, -122.419, "dog park")
            assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_graceful_failure_on_api_error(self):
        service = PlacesService(api_key="test-key")

        with patch("app.services.places.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await service.search_nearby(37.775, -122.419, "vet")

        assert results == []

    @pytest.mark.asyncio
    async def test_empty_api_key_returns_empty_list(self):
        service = PlacesService(api_key="")
        results = await service.search_nearby(37.775, -122.419, "vet")
        assert results == []

    @pytest.mark.asyncio
    async def test_cache_expiry(self):
        service = PlacesService(api_key="test-key")
        # Manually insert an expired cache entry
        cache_key = service._cache_key(37.775, -122.419, "vet")
        service._cache[cache_key] = (time.monotonic() - 8000, [{"name": "old"}])

        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_PLACES_API_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.places.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await service.search_nearby(37.775, -122.419, "vet")

        assert len(results) == 2  # Fresh results, not the stale cached one


# ---------------------------------------------------------------------------
# MapAgent tests
# ---------------------------------------------------------------------------


class TestMapAgent:
    """Test Map Agent with mocked LLM and Places service."""

    @pytest.mark.asyncio
    async def test_no_location_asks_user_to_share(self):
        agent = MapAgent()
        result = await agent.execute("find a vet", {"location": None, "pets": []})

        assert "share your location" in result["response"].lower()
        assert result["card"] is None

    @pytest.mark.asyncio
    async def test_no_location_key_asks_user_to_share(self):
        agent = MapAgent()
        result = await agent.execute("find a vet", {"pets": []})

        assert "share your location" in result["response"].lower()
        assert result["card"] is None

    @pytest.mark.asyncio
    @patch("app.agents.map_agent.places_service")
    @patch("app.agents.map_agent.litellm")
    async def test_returns_map_card_with_places(self, mock_litellm, mock_places):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response('{"query": "veterinary clinic", "explanation": "User needs a vet"}')
        )
        mock_places.search_nearby = AsyncMock(
            return_value=[
                {"name": "Vet A", "address": "1 St", "rating": 4.5, "place_id": "a", "lat": 37.77, "lng": -122.42, "open_now": True},
                {"name": "Vet B", "address": "2 St", "rating": 4.0, "place_id": "b", "lat": 37.78, "lng": -122.43, "open_now": None},
            ]
        )

        agent = MapAgent()
        result = await agent.execute(
            "find a vet nearby",
            {"location": {"lat": 37.7749, "lng": -122.4194}, "pets": []},
        )

        assert "Vet A" in result["response"]
        assert result["card"] is not None
        assert result["card"]["type"] == "map"
        assert result["card"]["query"] == "veterinary clinic"
        assert len(result["card"]["places"]) == 2

    @pytest.mark.asyncio
    @patch("app.agents.map_agent.places_service")
    @patch("app.agents.map_agent.litellm")
    async def test_no_results_returns_text_only(self, mock_litellm, mock_places):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response('{"query": "exotic bird vet", "explanation": "..."}')
        )
        mock_places.search_nearby = AsyncMock(return_value=[])

        agent = MapAgent()
        result = await agent.execute(
            "find an exotic bird vet",
            {"location": {"lat": 37.77, "lng": -122.42}, "pets": []},
        )

        assert "couldn't find" in result["response"].lower()
        assert result["card"] is None

    @pytest.mark.asyncio
    @patch("app.agents.map_agent.places_service")
    @patch("app.agents.map_agent.litellm")
    async def test_llm_failure_uses_fallback_query(self, mock_litellm, mock_places):
        mock_litellm.acompletion = AsyncMock(side_effect=Exception("LLM down"))
        mock_places.search_nearby = AsyncMock(
            return_value=[
                {"name": "Fallback Vet", "address": "99 St", "rating": 3.5, "place_id": "z", "lat": 37.77, "lng": -122.42, "open_now": True},
            ]
        )

        agent = MapAgent()
        result = await agent.execute(
            "where is a vet",
            {"location": {"lat": 37.77, "lng": -122.42}, "pets": []},
        )

        # Should still return results using fallback query "veterinary clinic"
        mock_places.search_nearby.assert_called_once()
        call_kwargs = mock_places.search_nearby.call_args.kwargs
        assert call_kwargs["query"] == "veterinary clinic"
        assert result["card"] is not None

    @pytest.mark.asyncio
    @patch("app.agents.map_agent.places_service")
    @patch("app.agents.map_agent.litellm")
    async def test_pet_context_passed_to_llm(self, mock_litellm, mock_places):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response('{"query": "dog park", "explanation": "..."}')
        )
        mock_places.search_nearby = AsyncMock(return_value=[])

        agent = MapAgent()
        await agent.execute(
            "where can I take my pet for a walk",
            {
                "location": {"lat": 37.77, "lng": -122.42},
                "pets": [{"name": "Buddy", "species": "dog"}],
            },
        )

        # Verify pet context was included in LLM call
        call_args = mock_litellm.acompletion.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "Buddy" in system_msg
        assert "dog" in system_msg
