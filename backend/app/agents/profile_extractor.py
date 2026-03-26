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
from app.config import settings

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
你是一个宠物信息提取器。分析用户的消息，判断是否包含宠物档案中应该记录的信息。

只提取**事实性的、持久的**宠物属性，不提取一次性事件（那些应该记到日历）。

应该提取的信息类型：
- 饮食习惯（日常吃什么、不吃什么、狗粮品牌）→ key: "diet"
- 性格特点（活泼、胆小、粘人、怕打雷）→ key: "temperament"
- 过敏信息（对鸡肉过敏）→ key: "allergies"
- 兽医/医院（去哪家医院、兽医叫什么）→ key: "vet"
- 毛色外观（金色、黑白花）→ key: "coat_color"
- 日常习惯（每天遛两次、喜欢玩球）→ key: "routine"
- 喜好厌恶（喜欢散步、怕洗澡）→ key: "preferences"
- 健康状况（膝关节有问题、心脏病）→ key: "health_notes"

不应该提取的：
- 一次性事件（今天吃了、刚打了疫苗、昨天吐了）→ 这些应该记到日历
- 问题（小薇能吃巧克力吗？）
- 闲聊（你好、谢谢）
- 已经是具体字段的信息（体重、生日、品种、性别）→ 这些由其他工具处理

回复格式（纯JSON，不要markdown）：
{"should_update": false}

或者：
{"should_update": true, "pet_name": "小薇", "info": {"diet": "主食肉类+红薯+蔬菜，不吃狗粮", "temperament": "活泼好动"}}

注意：
- info 的 value 应该是简洁的摘要，不是用户原话
- 可以同时提取多个字段
- 如果不确定是持久属性还是一次性事件，不要提取"""


async def extract_profile_info(
    message: str,
    pets: list,
) -> dict | None:
    """Analyze user message and extract profile-worthy info.

    Args:
        message: The user's raw message.
        pets: List of pet model instances.

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
    pet_context = "用户的宠物: " + ", ".join(pet_names)

    try:
        response = await litellm.acompletion(
            model=settings.executor_model,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": f"{pet_context}\n\n用户消息: {message}"},
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
