"""Miscellaneous intent detection: search_places, draft_email, summarize_profile,
set_avatar, language switch.
"""

import re
from datetime import date

from app.agents.locale import t
from .types import SuggestedAction
from .pet_utils import resolve_pets


_SEARCH_PLACES_PATTERN = re.compile(
    r"附近|哪里有|找一[下个家]|最近的|推荐.*(?:医院|宠物店|宠物医院|公园|狗公园)"
    r"|nearby|find.*(?:vet|clinic|pet store|park|hospital)"
    r"|where.*(?:vet|clinic|pet store|park)",
    re.I,
)

_DRAFT_EMAIL_PATTERN = re.compile(
    r"写.*邮件|草拟.*邮件|发.*邮件|帮我.*邮件|email|draft.*email|write.*email|compose.*email",
    re.I,
)

_SWITCH_LANGUAGE_PATTERN = re.compile(
    r"switch\s+to\s+(?:english|chinese|中文|英文)"
    r"|切换(?:成|到|为)?(?:中文|英文|english|chinese)"
    r"|(?:说|用|讲)(?:中文|英文|english|chinese)"
    r"|speak\s+(?:english|chinese)",
    re.I,
)

_INTRODUCE_PATTERN = re.compile(
    r"你能做什么|有什么功能|怎么用|能干[什嘛]么|你会[什嘛]么|介绍一下|你是谁|你是什么"
    r"|能记录什么|可以记录什么|记录.*推荐|还有什么.*记录|都能.*记录"
    r"|what can you do|how.*(?:use|work)|features|help me|what.*app.*do|who are you|what.*record",
    re.I,
)

_SUMMARIZE_PROFILE_PATTERN = re.compile(
    r"总结.*(?:档案|资料|信息)|更新.*档案|整理.*档案|summary.*profile"
    r"|summarize.*profile|汇总|生成.*报告",
    re.I,
)

_SET_AVATAR_PATTERN = re.compile(
    r"换.*头像|设.*头像|(?:这张|这个).*(?:做|当|设为).*头像|avatar|profile.*(?:pic|photo|image)",
    re.I,
)


def detect(
    message: str,
    pets: list,
    today: date,
    lang: str,
    is_question: bool,
) -> list[SuggestedAction]:
    """Detect miscellaneous intents and return suggested actions."""
    actions: list[SuggestedAction] = []

    # --- Search places ---
    # Not blocked by is_question — searching is a query but requires a tool call
    if _SEARCH_PLACES_PATTERN.search(message):
        actions.append(SuggestedAction(
            tool_name="search_places",
            arguments={"query": message[:100]},
            confidence=0.85,
            confirm_description=t("confirm_search_places", lang),
        ))

    # --- Draft email ---
    if not is_question and _DRAFT_EMAIL_PATTERN.search(message):
        actions.append(SuggestedAction(
            tool_name="draft_email",
            arguments={"subject": message[:50], "body": message},
            confidence=0.8,
            confirm_description=t("confirm_draft_email", lang),
        ))

    # --- Summarize pet profile ---
    if _SUMMARIZE_PROFILE_PATTERN.search(message) and pets:
        resolved_pets = resolve_pets(message, pets)
        for pet_id, pet_name in resolved_pets:
            actions.append(SuggestedAction(
                tool_name="summarize_pet_profile",
                arguments={"pet_id": pet_id},
                confidence=0.85,
                confirm_description=t("confirm_summarize_profile", lang).format(pet_name=pet_name),
            ))

    # --- Set pet avatar ---
    # Not blocked by is_question — setting avatar is an action
    if _SET_AVATAR_PATTERN.search(message) and pets:
        resolved_pets = resolve_pets(message, pets)
        for pet_id, pet_name in resolved_pets:
            actions.append(SuggestedAction(
                tool_name="set_pet_avatar",
                arguments={"pet_id": pet_id},
                confidence=0.85,
                confirm_description=t("confirm_set_avatar", lang).format(pet_name=pet_name),
            ))

    # --- Introduce product ---
    if _INTRODUCE_PATTERN.search(message):
        actions.append(SuggestedAction(
            tool_name="introduce_product",
            arguments={},
            confidence=0.9,
            confirm_description="Introduce product features",
        ))

    # --- Switch language ---
    if _SWITCH_LANGUAGE_PATTERN.search(message):
        # Determine target language
        target = "en"
        if re.search(r"中文|chinese", message, re.I):
            target = "zh"
        actions.append(SuggestedAction(
            tool_name="set_language",
            arguments={"language": target},
            confidence=0.9,
            confirm_description=f"Switch language to {'English' if target == 'en' else '中文'}",
        ))

    return actions
