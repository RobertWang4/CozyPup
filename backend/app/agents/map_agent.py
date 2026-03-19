"""Map Agent — finds nearby pet-related locations using Google Places."""

import json

import litellm

from app.agents.base import BaseAgent
from app.agents.prompts import MAP_PROMPT
from app.config import settings
from app.services.places import places_service


class MapAgent(BaseAgent):
    name = "map_agent"

    async def _run(self, message: str, context: dict, **kwargs) -> dict:
        """Find nearby places based on the user's request.

        Context keys:
            location: dict with "lat" and "lng", or None
            pets: list of pet objects for contextual search
        """
        location = context.get("location")

        # If no location, ask the user to share it
        if not location or "lat" not in location or "lng" not in location:
            return {
                "response": (
                    "I'd love to help you find nearby places! "
                    "Could you share your location so I can search for options near you?"
                ),
                "card": None,
            }

        lat = location["lat"]
        lng = location["lng"]

        # Build pet context string for the LLM
        pets = context.get("pets", [])
        pet_lines = []
        for pet in pets:
            name = getattr(pet, "name", None) or (pet.get("name") if isinstance(pet, dict) else None)
            species = getattr(pet, "species", None) or (pet.get("species") if isinstance(pet, dict) else None)
            if name and species:
                pet_lines.append(f"- {name} ({species})")
        pet_context = "\n".join(pet_lines) if pet_lines else "No pets on file."

        # Ask LLM to interpret the request into a search query
        llm_messages = [
            {"role": "system", "content": MAP_PROMPT.format(pet_context=pet_context)},
            {"role": "user", "content": message},
        ]

        try:
            response = await litellm.acompletion(
                model=settings.cheap_model,
                messages=llm_messages,
                temperature=0,
                max_tokens=150,
            )
            raw = response.choices[0].message.content.strip()
            parsed = json.loads(raw)
            query = parsed.get("query", "veterinary clinic")
        except Exception:
            # Fallback: use a generic query
            self.logger.warning("map_agent_llm_fallback", extra={"message_preview": message[:200]})
            query = "veterinary clinic"

        # Search Google Places
        places = await places_service.search_nearby(lat=lat, lng=lng, query=query)

        if not places:
            return {
                "response": f"I searched for \"{query}\" nearby but couldn't find any results. Try a different search or check your location.",
                "card": None,
            }

        # Build response text
        place_lines = []
        for i, p in enumerate(places[:5], 1):
            rating_str = f" ({p['rating']}★)" if p.get("rating") else ""
            place_lines.append(f"{i}. **{p['name']}**{rating_str} — {p['address']}")
        summary = f"Here are some nearby results for \"{query}\":\n\n" + "\n".join(place_lines)

        if len(places) > 5:
            summary += f"\n\n...and {len(places) - 5} more on the map."

        # Build map card
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
            "response": summary,
            "card": card,
        }
