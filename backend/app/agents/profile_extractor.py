"""Profile Extractor — lightweight sub-agent that runs in parallel with the main chat.

Analyzes each user message to detect pet profile-worthy information
(personality, habits, diet, health, preferences, etc.) and automatically
writes it to the pet's profile via update_pet_profile.

Uses a cheap model (deepseek-chat) with a single non-streaming call.
Does NOT generate user-facing text — purely a background data extraction task.
"""

import json
import logging

import litellm

from app.agents import llm_extra_kwargs
from app.agents.locale import t
from app.config import settings

logger = logging.getLogger(__name__)


async def extract_profile_info(
    message: str,
    pets: list,
    lang: str = "zh",
) -> dict | None:
    """Analyze user message and extract profile-worthy info.

    Args:
        message: The user's raw message.
        pets: List of pet model instances.
        lang: Language code for i18n ("zh" or "en").

    Returns:
        Dict with {"pet_id": ..., "info": {...}} if profile info found, else None.
    """
    if not pets or len(message.strip()) < 5:
        return None

    # Build pet context
    pet_names = []
    for p in pets:
        name = p.name if hasattr(p, "name") else p.get("name", "")
        pet_id = str(p.id if hasattr(p, "id") else p.get("id", ""))
        pet_names.append(f"{name}(id:{pet_id})")
    pet_context = f"{t('extractor_pets_label', lang)}: " + ", ".join(pet_names)

    try:
        response = await litellm.acompletion(
            model=settings.model,
            messages=[
                {"role": "system", "content": t("extraction_prompt", lang)},
                {"role": "user", "content": f"{pet_context}\n\n{t('extractor_message_label', lang)}: {message}"},
            ],
            temperature=0.1,
            stream=False,
            max_tokens=200,
            **llm_extra_kwargs(),
        )

        text = response.choices[0].message.content or ""
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        result = json.loads(text)

        if not result.get("should_update"):
            return None

        pet_name = result.get("pet_name", "")
        info = result.get("info", {})
        if not info:
            return None

        # Resolve pet_id from pet_name
        pet_id = None
        for p in pets:
            name = p.name if hasattr(p, "name") else p.get("name", "")
            pid = str(p.id if hasattr(p, "id") else p.get("id", ""))
            if name == pet_name or name.lower() == pet_name.lower():
                pet_id = pid
                break

        # If only one pet, use that one
        if not pet_id and len(pets) == 1:
            p = pets[0]
            pet_id = str(p.id if hasattr(p, "id") else p.get("id", ""))

        if not pet_id:
            return None

        logger.info("profile_extractor_found", extra={
            "pet_name": pet_name,
            "keys": list(info.keys()),
        })

        return {"pet_id": pet_id, "info": info}

    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.debug("profile_extractor_parse_error", extra={"error": str(exc)[:100]})
        return None
    except Exception as exc:
        logger.warning("profile_extractor_error", extra={"error": str(exc)[:200]})
        return None
