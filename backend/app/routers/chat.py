"""SSE stub endpoint for PetPal chat — returns canned responses for frontend dev."""

import asyncio
import json
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/v1", tags=["chat"])

HEALTH_DISCLAIMER = (
    "\n\n⚠️ This is general guidance only and not a substitute for "
    "professional veterinary advice. Please consult your vet for "
    "any health concerns."
)

EMERGENCY_KEYWORDS = {"seizure", "poison", "choking", "bleeding"}
CARD_KEYWORDS = {"record", "appointment", "vaccine"}

CANNED_RESPONSES = {
    "greeting": (
        "Hey there! 🐾 I'm PetPal, your friendly pet-health assistant. "
        "How can I help you and your furry friend today?"
    ),
    "health": (
        "Based on what you're describing, it sounds like your pet might "
        "benefit from a check-up. Common causes include dietary changes, "
        "seasonal allergies, or minor infections. Keep an eye on symptoms "
        "and make sure fresh water is always available."
    ),
    "emergency": (
        "This sounds like it could be urgent. Please stay calm and keep "
        "your pet as still and comfortable as possible while you seek "
        "immediate veterinary care."
    ),
    "general": (
        "Great question! Keeping your pet happy and healthy is all about "
        "consistency — regular meals, daily exercise, and lots of love. "
        "Let me know if you have a specific concern I can help with."
    ),
}

HEALTH_KEYWORDS = {
    "sick", "vomit", "diarrhea", "limp", "scratch", "itch",
    "cough", "sneeze", "lethargic", "eating", "weight", "symptom",
    "health", "vet", "medicine", "treatment", "diagnos",
}

GREETING_KEYWORDS = {"hello", "hi", "hey", "howdy", "morning", "evening"}


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


def _pick_response(message: str) -> tuple[str, str]:
    """Return (response_text, intent) based on keyword matching."""
    lower = message.lower()

    if any(kw in lower for kw in EMERGENCY_KEYWORDS):
        return CANNED_RESPONSES["emergency"], "emergency"

    if any(kw in lower for kw in HEALTH_KEYWORDS):
        return CANNED_RESPONSES["health"] + HEALTH_DISCLAIMER, "health"

    if any(kw in lower for kw in GREETING_KEYWORDS):
        return CANNED_RESPONSES["greeting"], "greeting"

    return CANNED_RESPONSES["general"], "chat"


def _detect_card(message: str) -> Optional[dict]:
    """Return a card payload if the message mentions card-worthy keywords."""
    lower = message.lower()
    for kw in CARD_KEYWORDS:
        if kw in lower:
            return {
                "type": kw if kw in ("record", "appointment") else "record",
                "pet_name": "Buddy",
                "date": date.today().isoformat(),
                "category": "abnormal" if kw == "record" else "upcoming",
            }
    return None


def _detect_emergency(message: str) -> Optional[dict]:
    """Return an emergency payload if the message contains emergency keywords."""
    lower = message.lower()
    if any(kw in lower for kw in EMERGENCY_KEYWORDS):
        return {"message": "Possible emergency detected", "action": "find_er"}
    return None


async def _event_generator(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    response_text, intent = _pick_response(request.message)

    # Stream tokens word-by-word
    words = response_text.split(" ")
    for i, word in enumerate(words):
        token = word if i == 0 else " " + word
        yield {
            "event": "token",
            "data": json.dumps({"text": token}),
        }
        await asyncio.sleep(0.05)

    # Card event (if applicable)
    card = _detect_card(request.message)
    if card:
        yield {
            "event": "card",
            "data": json.dumps(card),
        }

    # Emergency event (if applicable)
    emergency = _detect_emergency(request.message)
    if emergency:
        yield {
            "event": "emergency",
            "data": json.dumps(emergency),
        }

    # Done event — always last
    yield {
        "event": "done",
        "data": json.dumps({"intent": intent, "session_id": session_id}),
    }


@router.post("/chat")
async def chat(request: ChatRequest):
    return EventSourceResponse(_event_generator(request))
