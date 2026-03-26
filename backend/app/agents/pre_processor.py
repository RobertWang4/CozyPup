"""Deterministic pre-processor — extracts intent and pre-fills tool arguments
before the LLM sees the message.

When confidence is high (>= 0.8), the suggested actions are injected into the
system prompt so the LLM only needs to copy-paste the arguments into a tool call.

When confidence is medium (CONFIRM_THRESHOLD <= c < 0.8) AND values are
extractable, a confirm card is shown to the user for one-tap execution.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.agents.locale import t


CONFIRM_THRESHOLD = 0.5  # Minimum confidence for confirm card


@dataclass
class SuggestedAction:
    tool_name: str
    arguments: dict
    confidence: float  # 0.0 - 1.0
    confirm_description: str = ""  # Human-readable description for confirm card


# ---------- Date parsing ----------

_RELATIVE_DATES = {
    "今天": 0, "今日": 0, "today": 0,
    "明天": 1, "明日": 1, "tomorrow": 1,
    "后天": 2, "大后天": 3,
    "昨天": -1, "昨日": -1, "yesterday": -1,
    "前天": -2,
}


_AMBIGUOUS_DATE = re.compile(
    r"上周(?![一二三四五六日天])|上个?月(?!\d)|前阵子|前段时间|最近|之前"
    r"|last week(?!\s*(?:mon|tue|wed|thu|fri|sat|sun))|last month",
    re.I,
)

_WEEKDAY_LAST_WEEK = {
    "上周一": 0, "上周二": 1, "上周三": 2, "上周四": 3,
    "上周五": 4, "上周六": 5, "上周日": 6, "上周天": 6,
}


def _resolve_date(message: str, today: date) -> date | None:
    """Extract a date from the message.

    Returns None if the date is ambiguous (e.g. "上周" without specifying day).
    Returns today if no date info is found.
    """
    msg_lower = message.lower()

    # "上周一" → exact date
    for keyword, weekday in _WEEKDAY_LAST_WEEK.items():
        if keyword in msg_lower:
            days_back = (today.weekday() - weekday) % 7 + 7
            return today - timedelta(days=days_back)

    # Ambiguous dates → return None (caller should ask user)
    if _AMBIGUOUS_DATE.search(msg_lower):
        return None

    for keyword, delta in _RELATIVE_DATES.items():
        if keyword in msg_lower:
            return today + timedelta(days=delta)
    # Check for explicit dates like 3月23号, 3.23, 03-23
    m = re.search(r"(\d{1,2})[月.\-/](\d{1,2})[号日]?", message)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                return date(today.year, month, day)
            except ValueError:
                pass
    return today


# ---------- Pet name resolution ----------

def _resolve_pets(message: str, pets: list) -> list[tuple[str, str]]:
    """Find mentioned pets in the message. Returns list of (pet_id, pet_name).

    If no pet name is found and there's only one pet, use that one.
    If no pet name is found and there are multiple pets, return all.
    """
    mentioned = []
    msg_lower = message.lower()
    for pet in pets:
        pet_name = pet.name if hasattr(pet, "name") else pet.get("name", "")
        pet_id = str(pet.id if hasattr(pet, "id") else pet.get("id", ""))
        if pet_name.lower() in msg_lower:
            mentioned.append((pet_id, pet_name))

    if mentioned:
        return mentioned
    if len(pets) == 1:
        p = pets[0]
        return [(str(p.id if hasattr(p, "id") else p.get("id", "")),
                 p.name if hasattr(p, "name") else p.get("name", ""))]
    # Ambiguous — return all so caller can decide
    return [
        (str(p.id if hasattr(p, "id") else p.get("id", "")),
         p.name if hasattr(p, "name") else p.get("name", ""))
        for p in pets
    ]


# ---------- Value extraction ----------

def _extract_new_name(message: str) -> str | None:
    """Extract the new pet name from a rename message."""
    patterns = [
        r"(?:改|换)(?:成|为|做|叫)\s*[「「\"']?(.+?)[」」\"']?\s*(?:吧|了|呢|啊|$)",
        r"名字.*?(?:是|叫)\s*[「「\"']?(.+?)[」」\"']?\s*(?:[,，。]|你|帮|改|$)",
        r"rename\s+(?:to\s+)?(\S+)",
        r"change\s+name\s+to\s+(\S+)",
    ]
    for p in patterns:
        m = re.search(p, message.strip(), re.I)
        if m:
            name = m.group(1).strip().rstrip("。，,.!！?？ ")
            if 1 <= len(name) <= 20:
                return name
    return None


def _extract_weight(message: str) -> float | None:
    """Extract weight in kg from message."""
    # Match patterns like "5kg", "5公斤", "10斤"
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|公斤)", message, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*斤", message)
    if m:
        return float(m.group(1)) / 2  # 斤 to kg
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:lb|lbs|pounds?)", message, re.I)
    if m:
        return round(float(m.group(1)) * 0.4536, 1)
    return None


def _extract_birthday(message: str) -> str | None:
    """Extract birthday as YYYY-MM-DD string."""
    # "2024年3月5日" or "2024-03-05"
    m = re.search(r"(\d{4})[年.\-/](\d{1,2})[月.\-/](\d{1,2})[日号]?", message)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return d.isoformat()
        except ValueError:
            pass
    # "3月5号" — assume current year
    m = re.search(r"(\d{1,2})[月.\-/](\d{1,2})[日号]?", message)
    if m:
        try:
            d = date(date.today().year, int(m.group(1)), int(m.group(2)))
            return d.isoformat()
        except ValueError:
            pass
    return None


def _extract_gender(message: str) -> str | None:
    """Extract gender from message."""
    if re.search(r"公的|公狗|公猫|male|boy|男", message, re.I):
        return "male"
    if re.search(r"母的|母狗|母猫|female|girl|女", message, re.I):
        return "female"
    return None


# ---------- Intent patterns ----------

_CALENDAR_PATTERNS = [
    # (regex, category, confidence)
    (re.compile(r"吃了|喂了|喂食|吃的|feeding|fed|ate|kibble", re.I), "diet", 0.9),
    (re.compile(r"拉了|拉稀|拉肚子|大便|排便|excretion|poop", re.I), "excretion", 0.9),
    (re.compile(r"吐了|呕吐|vomit|不舒服|不太好|sick|异常", re.I), "abnormal", 0.9),
    (re.compile(r"打了.*疫苗|接种|vaccin", re.I), "vaccine", 0.9),
    (re.compile(r"驱虫|deworm", re.I), "deworming", 0.9),
    (re.compile(r"看医生|去医院|看兽医|vet visit|checkup|体检", re.I), "medical", 0.85),
    (re.compile(r"遛了|遛狗|散步|走了|洗澡|grooming|walk|park|公园", re.I), "daily", 0.85),
]

_QUESTION_OVERRIDE = re.compile(
    r"[?？]|怎么|为什么|多久|多少|上次|最近|几次|哪天|什么时候"
    r"|how|when|why|what|last time|should|可以吗|能不能|要不要|是不是|好不好",
    re.I,
)

_CREATE_PET_PATTERN = re.compile(
    r"新养了|新.*(?:狗|猫|宠物)|养了.*(?:叫|名字)|创建.*宠物|添加.*宠物|新来了|刚买了|刚领养"
    r"|got a new|new (?:pet|puppy|kitten|dog|cat)|adopt",
    re.I,
)

_UPDATE_PROFILE_PATTERNS = [
    # (regex, key, confidence)
    (re.compile(r"改名|名字.*改|名字.*换|名字.*叫|更名|rename|change.*name", re.I), "name", 0.9),
    (re.compile(r"生日[是在]|birthday", re.I), "birthday", 0.85),
    (re.compile(r"体重[是有]?|重.*?(?:斤|kg|公斤)|weigh", re.I), "weight", 0.85),
    (re.compile(r"过敏|allerg", re.I), "allergies", 0.85),
    (re.compile(r"是公的|是母的|公狗|母狗|male|female|gender|性别", re.I), "gender", 0.85),
    (re.compile(r"绝育|neutered|spayed", re.I), "neutered", 0.85),
    (re.compile(r"品种[是叫]|breed|是.*?(?:金毛|泰迪|柯基|柴犬|拉布拉多|哈士奇|边牧|法斗|比熊|博美|萨摩|秋田|雪纳瑞|马犬|贵宾|可卡|巴哥)", re.I), "breed", 0.85),
    (re.compile(r"饮食|吃的|狗粮|猫粮|diet|food|kibble|每天吃", re.I), "diet", 0.8),
    (re.compile(r"兽医|医院|vet|doctor|clinic", re.I), "vet", 0.8),
    (re.compile(r"毛色|颜色|coat|color", re.I), "coat_color", 0.8),
    (re.compile(r"性格|脾气|temperament|personality|怕|胆小|活泼|温顺", re.I), "temperament", 0.8),
]

_REMINDER_PATTERNS = [
    (re.compile(r"提醒我|别忘了|记得|remind me|don't forget|set.*reminder", re.I), 0.85),
]

_REMINDER_TYPES_MAP = [
    (re.compile(r"喂药|吃药|medication|medicine", re.I), "medication"),
    (re.compile(r"疫苗|打针|vaccin", re.I), "vaccine"),
    (re.compile(r"体检|检查|checkup", re.I), "checkup"),
    (re.compile(r"喂食|喂饭|feeding|feed", re.I), "feeding"),
    (re.compile(r"洗澡|美容|grooming|groom|bath", re.I), "grooming"),
]

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

_SUMMARIZE_PROFILE_PATTERN = re.compile(
    r"总结.*(?:档案|资料|信息)|更新.*档案|整理.*档案|summary.*profile"
    r"|summarize.*profile|汇总|生成.*报告",
    re.I,
)

_SET_AVATAR_PATTERN = re.compile(
    r"换.*头像|设.*头像|(?:这张|这个).*(?:做|当|设为).*头像|avatar|profile.*(?:pic|photo|image)",
    re.I,
)

# Value extractors by key — returns extracted value or None
_VALUE_EXTRACTORS: dict[str, callable] = {
    "name": _extract_new_name,
    "birthday": _extract_birthday,
    "weight": _extract_weight,
    "gender": _extract_gender,
}


# ---------- Main entry point ----------

def pre_process(
    message: str,
    pets: list,
    today: date | None = None,
    lang: str = "zh",
) -> list[SuggestedAction]:
    """Analyze user message and return suggested tool calls with pre-filled arguments.

    Args:
        message: The user's raw message text.
        pets: List of Pet model instances or dicts with id/name fields.
        today: Override for today's date (for testing).

    Returns:
        List of SuggestedAction. Empty if no action detected.
    """
    if today is None:
        today = date.today()

    # If the message is clearly a question, don't suggest recording actions
    is_question = bool(_QUESTION_OVERRIDE.search(message))

    actions: list[SuggestedAction] = []

    # --- Calendar events ---
    if not is_question:
        for pattern, category, confidence in _CALENDAR_PATTERNS:
            if pattern.search(message):
                event_date = _resolve_date(message, today)
                resolved_pets = _resolve_pets(message, pets)

                # Ambiguous date (e.g. "上周") → skip pre-processing, let LLM ask
                if event_date is None:
                    continue

                # Check if a specific pet was mentioned by name
                mentioned_names = [
                    p.name if hasattr(p, "name") else p.get("name", "")
                    for p in pets
                    if (p.name if hasattr(p, "name") else p.get("name", "")).lower() in message.lower()
                ]

                if mentioned_names:
                    # Specific pet(s) mentioned → one event per mentioned pet
                    for pet_id, pet_name in resolved_pets:
                        if pet_name in mentioned_names:
                            actions.append(SuggestedAction(
                                tool_name="create_calendar_event",
                                arguments={
                                    "pet_id": pet_id,
                                    "event_date": event_date.isoformat(),
                                    "title": message[:100],
                                    "category": category,
                                    "raw_text": message,
                                },
                                confidence=confidence,
                                confirm_description=t("confirm_record_for_pet", lang).format(pet_name=pet_name, category=category, date=event_date.isoformat()),
                            ))
                elif len(pets) == 1:
                    # Only one pet → assign to that pet
                    pet_id, pet_name = resolved_pets[0]
                    actions.append(SuggestedAction(
                        tool_name="create_calendar_event",
                        arguments={
                            "pet_id": pet_id,
                            "event_date": event_date.isoformat(),
                            "title": message[:100],
                            "category": category,
                            "raw_text": message,
                        },
                        confidence=confidence,
                        confirm_description=f"为{pet_name}记录 {category}（{event_date.isoformat()}）",
                    ))
                else:
                    # Multiple pets, none mentioned → ONE shared event, no pet_id
                    actions.append(SuggestedAction(
                        tool_name="create_calendar_event",
                        arguments={
                            "event_date": event_date.isoformat(),
                            "title": message[:100],
                            "category": category,
                            "raw_text": message,
                        },
                        confidence=confidence,
                        confirm_description=t("confirm_record", lang).format(category=category, date=event_date.isoformat()),
                    ))

    # --- Create pet ---
    if _CREATE_PET_PATTERN.search(message):
        # Extract name if possible (e.g., "叫豆豆" → "豆豆")
        name_match = re.search(r"叫(\S+)", message)
        name = name_match.group(1) if name_match else ""

        # Extract species
        species = None
        if re.search(r"猫|cat|kitten", message, re.I):
            species = "cat"
        elif re.search(r"狗|dog|puppy", message, re.I):
            species = "dog"

        # Extract breed
        breed_match = re.search(
            r"(金毛|泰迪|柯基|柴犬|拉布拉多|哈士奇|边牧|法斗|比熊|博美|萨摩|秋田|雪纳瑞|马犬|贵宾|可卡|巴哥"
            r"|golden retriever|labrador|corgi|husky|poodle|bulldog|shiba|beagle|chihuahua)",
            message, re.I,
        )
        breed = breed_match.group(1) if breed_match else None

        # Extract gender and birthday
        gender = _extract_gender(message)
        birthday = _extract_birthday(message)

        if name:
            args = {"name": name, "species": species or "dog"}
            if breed:
                args["breed"] = breed
            if gender:
                args["gender"] = gender
            if birthday:
                args["birthday"] = birthday

            # Higher confidence when both name and species are extracted
            conf = 0.85 if (name and species) else 0.7

            actions.append(SuggestedAction(
                tool_name="create_pet",
                arguments=args,
                confidence=conf,
                confirm_description=t("confirm_add_pet", lang).format(name=name),
            ))

    # --- Reminders ---
    # Reminder patterns should NOT be blocked by is_question (reminders are future actions)
    for pattern, confidence in _REMINDER_PATTERNS:
        if pattern.search(message):
            # Infer reminder type
            reminder_type = "other"
            for type_pattern, type_name in _REMINDER_TYPES_MAP:
                if type_pattern.search(message):
                    reminder_type = type_name
                    break

            trigger_date = _resolve_date(message, today)
            trigger_at = datetime.combine(trigger_date, datetime.min.replace(hour=9).time()).isoformat()

            resolved_pets = _resolve_pets(message, pets) if pets else []

            if resolved_pets:
                for pet_id, pet_name in resolved_pets:
                    actions.append(SuggestedAction(
                        tool_name="create_reminder",
                        arguments={
                            "pet_id": pet_id,
                            "title": message[:100],
                            "type": reminder_type,
                            "trigger_at": trigger_at,
                        },
                        confidence=confidence,
                        confirm_description=t("confirm_reminder_for_pet", lang).format(pet_name=pet_name, type=reminder_type, date=trigger_date.isoformat()),
                    ))
            else:
                actions.append(SuggestedAction(
                    tool_name="create_reminder",
                    arguments={
                        "title": message[:100],
                        "type": reminder_type,
                        "trigger_at": trigger_at,
                    },
                    confidence=confidence,
                    confirm_description=t("confirm_reminder", lang).format(type=reminder_type, date=trigger_date.isoformat()),
                ))
            break  # Only match first reminder pattern

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
        resolved_pets = _resolve_pets(message, pets)
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
        resolved_pets = _resolve_pets(message, pets)
        for pet_id, pet_name in resolved_pets:
            actions.append(SuggestedAction(
                tool_name="set_pet_avatar",
                arguments={"pet_id": pet_id},
                confidence=0.85,
                confirm_description=t("confirm_set_avatar", lang).format(pet_name=pet_name),
            ))

    # --- Update pet profile ---
    if not is_question and pets:
        resolved_pets = _resolve_pets(message, pets)
        for pattern, key, conf in _UPDATE_PROFILE_PATTERNS:
            if pattern.search(message):
                # Try to extract the actual value
                extractor = _VALUE_EXTRACTORS.get(key)
                extracted = extractor(message) if extractor else None

                for pet_id, pet_name in resolved_pets:
                    # Free-text fields: use the raw message as value (LLM would do the same)
                    FREE_TEXT_FIELDS = {"diet", "vet", "temperament", "allergies", "coat_color"}
                    if extracted is not None:
                        # We have a concrete value — can be used for confirm card
                        args = {"pet_id": pet_id, "info": {key: extracted}}
                        desc = t("confirm_update_pet_key", lang).format(pet_name=pet_name, key=key, value=extracted)
                    elif key in FREE_TEXT_FIELDS:
                        # Free-text: use raw message, keep confidence high
                        args = {"pet_id": pet_id, "info": {key: message[:200]}}
                        desc = t("confirm_update_pet", lang).format(pet_name=pet_name, key=key)
                    else:
                        # Structured fields without extractor — need LLM
                        args = {"pet_id": pet_id, "info": {key: message}}
                        desc = t("confirm_update_pet", lang).format(pet_name=pet_name, key=key)
                        conf = min(conf, 0.7)

                    actions.append(SuggestedAction(
                        tool_name="update_pet_profile",
                        arguments=args,
                        confidence=conf,
                        confirm_description=desc,
                    ))
                break

    return actions
