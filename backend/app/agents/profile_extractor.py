"""Profile Extractor — lightweight sub-agent that runs in parallel with the main chat.

Two-step process:
  1. Analyze message → decide if profile-worthy info exists (JSON output)
  2. If yes → LLM merges new info into existing profile_md (free-text markdown)

The profile_md is an open-ended knowledge base for the AI. No fixed schema —
the AI decides what to record and how to organize it. This gives future
conversations full context about the pet's health, habits, personality, etc.
"""

import json
import logging

import litellm

from app.agents import llm_extra_kwargs
from app.agents.locale import t
from app.config import settings

logger = logging.getLogger(__name__)

_MERGE_PROMPT = {
    "zh": """你是宠物档案编辑器。把新信息合并到现有档案中。

规则：
1. 保留现有档案的所有内容，不要删除任何信息
2. 把新信息插入到合适的分区下（如 ## 健康、## 性格、## 日常）
3. 如果没有合适的分区，创建一个新分区
4. 如果新信息和已有内容冲突，用新信息替换旧的
5. 保持简洁，用短句
6. 只输出完整的档案 markdown，不要其他内容
7. 不要超过 500 字""",
    "en": """You are a pet profile editor. Merge new information into the existing profile.

Rules:
1. Keep all existing content — never delete information
2. Insert new info under the appropriate section (e.g. ## Health, ## Personality, ## Daily)
3. If no suitable section exists, create a new one
4. If new info conflicts with existing content, replace the old with the new
5. Keep it concise, use short phrases
6. Output only the complete profile markdown, nothing else
7. Stay under 500 words""",
}


async def extract_profile_info(
    message: str,
    pets: list,
    lang: str = "zh",
) -> dict | None:
    """Step 1: Analyze user message and extract profile-worthy info.

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


async def merge_into_profile_md(
    pet,
    info: dict,
    lang: str = "zh",
) -> str | None:
    """Step 2: LLM merges extracted info into the pet's profile_md.

    Args:
        pet: Pet ORM object (needs .profile_md, .name)
        info: Dict of extracted info, e.g. {"vaccination": "三针已完成"}

    Returns:
        New profile_md string, or None on failure.
    """
    existing_md = pet.profile_md or f"# {pet.name}\n\n## 基本信息\n"
    new_info_text = "\n".join(f"- {k}: {v}" for k, v in info.items())

    try:
        response = await litellm.acompletion(
            model=settings.model,
            messages=[
                {"role": "system", "content": _MERGE_PROMPT.get(lang, _MERGE_PROMPT["zh"])},
                {"role": "user", "content": f"现有档案:\n{existing_md}\n\n新信息:\n{new_info_text}"},
            ],
            temperature=0.1,
            stream=False,
            max_tokens=800,
            **llm_extra_kwargs(),
        )

        new_md = response.choices[0].message.content or ""
        new_md = new_md.strip()
        # Strip markdown code fences if present
        if new_md.startswith("```"):
            new_md = new_md.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        if len(new_md) < 10:
            return None

        logger.info("profile_md_merged", extra={
            "pet_name": pet.name,
            "new_keys": list(info.keys()),
            "md_length": len(new_md),
        })

        return new_md

    except Exception as exc:
        logger.warning("profile_md_merge_error", extra={"error": str(exc)[:200]})
        return None
