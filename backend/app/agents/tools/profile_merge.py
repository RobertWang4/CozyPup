"""Merge two pet profile_md documents using an LLM.

Used when pet sharing transfers a pet between owners — both owners may
have independently edited the pet's narrative profile, and we need a
single reconciled document. Falls back to concatenation if the LLM
call fails so we never lose data.
"""

import logging

import litellm

from app.agents import llm_extra_kwargs
from app.config import settings

logger = logging.getLogger(__name__)


async def merge_pet_profiles(profile_a: str | None, profile_b: str | None) -> str | None:
    """Use LLM to merge two pet profile documents. Returns merged markdown."""
    if not profile_a and not profile_b:
        return None
    if not profile_a:
        return profile_b
    if not profile_b:
        return profile_a

    prompt = (
        "Merge these two pet profile documents into one cohesive document.\n"
        "Keep all unique information from both profiles.\n"
        "When information conflicts, prefer Profile A (the primary owner's version).\n"
        "Output a single markdown document, under 500 words.\n\n"
        f"## Profile A (primary):\n{profile_a}\n\n"
        f"## Profile B (secondary):\n{profile_b}\n\n"
        "Output ONLY the merged profile document, no explanation."
    )

    try:
        response = await litellm.acompletion(
            model=settings.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1000,
            **llm_extra_kwargs(),
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("profile_merge_error", extra={"error": str(exc)[:200]})
        return f"{profile_a}\n\n---\n\n{profile_b}"
