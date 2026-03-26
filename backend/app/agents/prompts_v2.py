"""
V2 Prompt Builder — cache-friendly ordering for prefix caching.

Prompt structure (static -> dynamic for maximum cache hit):
  1. Tool definitions + decision tree  (100% cache hit -- never changes)
  2. Pet profiles (profile_md/JSON)    (high cache hit -- rarely changes)
  3. Session summary                   (changes occasionally)
  4. Recent raw messages (3-5)         (changes every request)
  5. Emergency hint                    (dynamic, optional)
  6. Pre-processor hints               (dynamic, optional)
"""

import json

from app.agents.locale import t


def build_system_prompt(
    pets: list | None = None,
    session_summary: dict | None = None,
    emergency_hint: str | None = None,
    preprocessor_hints: list[str] | None = None,
    today: str = "",
    lang: str = "zh",
) -> str:
    """
    Build the system prompt in cache-friendly order.
    Static content first (tool guide, base prompt), dynamic content last.
    """
    parts: list[str] = []

    # 1. Static: base prompt + tool decision tree (100% cache hit)
    parts.append(t("base_system_prompt", lang))
    parts.append(t("tool_decision_tree", lang))

    # 2. Semi-static: pet profiles (high cache hit)
    if pets:
        parts.append(_build_pet_context(pets, lang=lang))
    else:
        parts.append(t("no_pets", lang))

    # Today's date
    if today:
        parts.append(t("today_date", lang).format(today=today))

    # 3. Session summary (changes occasionally)
    if session_summary:
        parts.append(_build_summary_section(session_summary, lang=lang))

    # 4/5. Dynamic hints (changes every request)
    if emergency_hint:
        parts.append(f"\n{emergency_hint}")

    if preprocessor_hints:
        hints_text = "\n".join(f"- {h}" for h in preprocessor_hints)
        parts.append(t("preprocessor_hint", lang).format(hints=hints_text))

    return "\n".join(parts)


def build_messages(
    recent_messages: list[dict],
    user_message: str,
    images: list[str] | None = None,
) -> list[dict]:
    """
    Build the messages list with recent history + current user message.
    Uses only recent 3-5 unsummarized messages (not full 20).
    """
    messages: list[dict] = []

    # Recent messages (already filtered to 3-5 by caller)
    # Content may be a string or multimodal list (when images are included)
    for msg in recent_messages:
        messages.append({
            "role": msg.get("role", "user"),
            "content": msg.get("content") or "",
        })

    # Current user message (with optional images)
    if images:
        user_content: list[dict] = [{"type": "text", "text": user_message}]
        for img_b64 in images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
            })
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": user_message})

    return messages


def _build_pet_context(pets: list, lang: str = "zh") -> str:
    """Build pet context section for system prompt."""
    lines = [t("pet_section_header", lang)]
    for p in pets:
        name = p.name if hasattr(p, "name") else p.get("name", "")
        pet_id = p.id if hasattr(p, "id") else p.get("id", "")
        species_val = (
            p.species.value
            if hasattr(p, "species") and hasattr(p.species, "value")
            else str(p.get("species", ""))
        )

        info = [f"- **{name}** (id: {pet_id}): {species_val}"]

        # Show locked field status
        profile = p.profile if hasattr(p, "profile") else p.get("profile")
        profile_dict = profile if isinstance(profile, dict) else {}
        species_locked = p.species_locked if hasattr(p, "species_locked") else p.get("species_locked", False)
        gender = profile_dict.get("gender")
        gender_locked = profile_dict.get("gender_locked", False)
        if gender:
            lock_icon = "🔒" if gender_locked else ""
            info.append(f"{t('gender_label', lang)}={gender}{lock_icon}")
        if species_locked:
            info.append(t("species_locked", lang))

        breed = p.breed if hasattr(p, "breed") else p.get("breed")
        if breed:
            info.append(f"{t('breed_label', lang)}={breed}")

        weight = p.weight if hasattr(p, "weight") else p.get("weight")
        if weight:
            info.append(f"{t('weight_label', lang)}={weight}kg")

        birthday = p.birthday if hasattr(p, "birthday") else p.get("birthday")
        if birthday:
            bday_str = birthday.isoformat() if hasattr(birthday, "isoformat") else str(birthday)
            info.append(f"{t('birthday_label', lang)}={bday_str}")

        lines.append(", ".join(info))

        profile_md = p.profile_md if hasattr(p, "profile_md") else p.get("profile_md")
        if profile_md:
            lines.append(f"\n### {name}{t('profile_header', lang)}\n{profile_md}")
        else:
            profile = p.profile if hasattr(p, "profile") else p.get("profile")
            if profile:
                profile_str = json.dumps(profile, ensure_ascii=False)
                lines.append(f"  {t('profile_label', lang)}: {profile_str}")

    return "\n".join(lines)


def _build_summary_section(summary: dict, lang: str = "zh") -> str:
    """Format session summary for prompt injection."""
    parts = [t("summary_header", lang)]

    topics = summary.get("topics", [])
    if topics:
        parts.append(f"{t('summary_topics', lang)}: {', '.join(topics)}")

    key_facts = summary.get("key_facts", [])
    if key_facts:
        parts.append(f"{t('summary_key_facts', lang)}:")
        for fact in key_facts:
            parts.append(f"  - {fact}")

    pending = summary.get("pending")
    if pending:
        parts.append(f"{t('summary_pending', lang)}: {pending}")

    mood = summary.get("mood")
    if mood and mood != "neutral" and mood != "unknown":
        parts.append(f"{t('summary_mood', lang)}: {mood}")

    return "\n".join(parts)
