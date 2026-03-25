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
- 用简短、温暖的语气回复
- title 字段必须是 2-8 字的简短摘要，不要使用用户的原始句子
- 一次只执行一个任务，除非用户明确提到多件事
- 不确定时询问用户，不要猜测"""


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
    for msg in recent_messages:
        messages.append({
            "role": msg.get("role", "user"),
            "content": msg.get("content", ""),
        })

    # Current user message (with optional images)
    if images:
        from app.config import settings
        import base64
        from pathlib import Path
        import uuid as _uuid

        temp_dir = Path(__file__).resolve().parent.parent / "uploads" / "temp_images"
        temp_dir.mkdir(parents=True, exist_ok=True)

        user_content: list[dict] = [{"type": "text", "text": user_message}]
        for img_b64 in images:
            fname = f"{_uuid.uuid4().hex}.jpg"
            fpath = temp_dir / fname
            fpath.write_bytes(base64.b64decode(img_b64))
            img_url = f"{settings.server_public_url}/temp-images/{fname}"
            user_content.append({
                "type": "image_url",
                "image_url": {"url": img_url},
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
