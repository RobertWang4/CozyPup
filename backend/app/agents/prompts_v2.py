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

from app.agents.tool_guide import TOOL_DECISION_TREE


BASE_SYSTEM_PROMPT = """你是 CozyPup，一个专业的宠物健康助手。你通过自然对话帮助用户管理宠物的健康和日常生活。

你的职责:
- 记录宠物的饮食、排泄、运动、疫苗、就医等日常事件
- 回答宠物健康和护理相关问题
- 设置提醒（疫苗、驱虫、喂药等）
- 在紧急情况下提供急救指导并帮助找到最近的宠物医院

规则:
- 【语言】你必须使用用户发消息时使用的语言来回复。用户用英文就用英文回复，用户用中文就用中文回复，用户用日文就用日文回复。绝对不要自行切换语言
- 用简短、温暖的语气回复
- title 字段必须是 2-8 字的简短摘要，不要使用用户的原始句子
- 如果用户一句话提到了多件不同的事（如"去了公园还吃了药"），必须拆分为多个独立的工具调用，每件事一个 create_calendar_event，不要合并成一条记录
- 不确定时询问用户，不要猜测
- 【模糊日期】用户说"上周""上个月""之前""前阵子"等没有具体日期时，必须追问"上周几？"或"大概几号？"，不要自己猜一个日期直接记录。只有"上周一""上周三"这种明确的才可以直接记录
- 【纠正记录】用户纠正已记录的信息时（如"不是周三是周一"），应该用 update_calendar_event 修改原记录的日期，不要新建一条重复记录
- 【重要】任何涉及数据变更的操作（更新信息、记录事件、换头像、设提醒等）都必须调用对应的工具来执行。绝对不要用文字回复假装已经完成了操作。如果没有调用工具，就不要说"已更新""已记录"等字眼
- 【锁定字段】性别和物种一旦设定就永久锁定，不可修改。如果用户要求修改已锁定的性别或物种，礼貌地告知该信息已设定且无法更改，不要尝试调用工具修改
- 【禁止捏造数据】只传用户明确提到的字段。用户没说体重就不要传 weight，没说生日就不要传 birthday。捏造数据和谎报工具调用一样严重。同时，用户提到的每个信息都必须传到工具参数里，不能遗漏
- 【禁止暴露内部信息】不要在回复中展示 UUID、event_id、pet_id 等内部标识符。用户不需要看到这些。用事件标题、日期、宠物名字等自然语言描述即可
- 【回复格式】回复末尾不要有空行或多余空格
- 【删除/修改流程】用户要求删除或修改某条记录时，在同一轮回复中完成：先 query_calendar_events 查到记录，然后直接调 delete/update 工具并附上确认卡片。不要查到后停下来问用户"是这条吗？"——直接执行，确认卡片会让用户最终确认

图片处理规则:
- 用户发了图片时，先看图片内容，理解图片中的宠物外观（毛色、品种、状态等）
- 如果用户要求换头像/存日记：执行对应工具，同时可以简短描述图片内容
- 如果用户问图片相关问题（这是什么/什么颜色/什么品种）：仔细分析图片后回答
- 如果用户只发图片没有文字：描述图片内容，问用户想做什么（换头像？记录到日记？）
- 永远根据你实际看到的图片回答，不要猜测图片内容"""


def build_system_prompt(
    pets: list | None = None,
    session_summary: dict | None = None,
    emergency_hint: str | None = None,
    preprocessor_hints: list[str] | None = None,
    today: str = "",
) -> str:
    """
    Build the system prompt in cache-friendly order.
    Static content first (tool guide, base prompt), dynamic content last.
    """
    parts: list[str] = []

    # 1. Static: base prompt + tool decision tree (100% cache hit)
    parts.append(BASE_SYSTEM_PROMPT)
    parts.append(TOOL_DECISION_TREE)

    # 2. Semi-static: pet profiles (high cache hit)
    if pets:
        parts.append(_build_pet_context(pets))
    else:
        parts.append("\n用户还没有添加宠物。")

    # Today's date
    if today:
        parts.append(f"\n今天日期: {today}")

    # 3. Session summary (changes occasionally)
    if session_summary:
        parts.append(_build_summary_section(session_summary))

    # 4/5. Dynamic hints (changes every request)
    if emergency_hint:
        parts.append(f"\n{emergency_hint}")

    if preprocessor_hints:
        hints_text = "\n".join(f"- {h}" for h in preprocessor_hints)
        parts.append(
            f"\n💡 系统检测到以下可能的意图（仅供参考，请自行判断）:\n{hints_text}"
        )

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


def _build_pet_context(pets: list) -> str:
    """Build pet context section for system prompt."""
    lines = ["\n## 用户的宠物"]
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
            info.append(f"性别={gender}{lock_icon}")
        if species_locked:
            info.append("物种=🔒已锁定")

        breed = p.breed if hasattr(p, "breed") else p.get("breed")
        if breed:
            info.append(f"品种={breed}")

        weight = p.weight if hasattr(p, "weight") else p.get("weight")
        if weight:
            info.append(f"体重={weight}kg")

        birthday = p.birthday if hasattr(p, "birthday") else p.get("birthday")
        if birthday:
            bday_str = birthday.isoformat() if hasattr(birthday, "isoformat") else str(birthday)
            info.append(f"生日={bday_str}")

        lines.append(", ".join(info))

        profile_md = p.profile_md if hasattr(p, "profile_md") else p.get("profile_md")
        if profile_md:
            lines.append(f"\n### {name} 的档案\n{profile_md}")
        else:
            profile = p.profile if hasattr(p, "profile") else p.get("profile")
            if profile:
                profile_str = json.dumps(profile, ensure_ascii=False)
                lines.append(f"  档案: {profile_str}")

    return "\n".join(lines)


def _build_summary_section(summary: dict) -> str:
    """Format session summary for prompt injection."""
    parts = ["\n## 今日对话摘要"]

    topics = summary.get("topics", [])
    if topics:
        parts.append(f"话题: {', '.join(topics)}")

    key_facts = summary.get("key_facts", [])
    if key_facts:
        parts.append("重要信息:")
        for fact in key_facts:
            parts.append(f"  - {fact}")

    pending = summary.get("pending")
    if pending:
        parts.append(f"待办: {pending}")

    mood = summary.get("mood")
    if mood and mood != "neutral" and mood != "unknown":
        parts.append(f"用户情绪: {mood}")

    return "\n".join(parts)
