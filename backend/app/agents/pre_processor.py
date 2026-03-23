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
from datetime import date, timedelta


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


def _resolve_date(message: str, today: date) -> date:
    """Extract a date from the message. Defaults to today."""
    for keyword, delta in _RELATIVE_DATES.items():
        if keyword in message.lower():
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
    r"新养了|新.*(?:狗|猫|宠物)|养了.*(?:叫|名字)|got a new|new (?:pet|puppy|kitten|dog|cat)",
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
]

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
                # If multiple pets and none mentioned by name, lower confidence
                # so LLM decides (it should ask which pet)
                actual_confidence = confidence
                if len(resolved_pets) > 1 and len(pets) > 1:
                    mentioned_names = [p.name if hasattr(p, "name") else p.get("name", "")
                                       for p in pets
                                       if (p.name if hasattr(p, "name") else p.get("name", "")).lower() in message.lower()]
                    if not mentioned_names:
                        actual_confidence = 0.5  # below 0.8 threshold, won't be injected
                for pet_id, pet_name in resolved_pets:
                    actions.append(SuggestedAction(
                        tool_name="create_calendar_event",
                        arguments={
                            "pet_id": pet_id,
                            "event_date": event_date.isoformat(),
                            "title": message[:100],  # LLM will refine this
                            "category": category,
                            "raw_text": message,
                        },
                        confidence=actual_confidence,
                        confirm_description=f"为{pet_name}记录 {category} 事件（{event_date.isoformat()}）",
                    ))
                # No break — continue matching so multiple intents are detected
                # (e.g., "vaccination + deworming" → two create_calendar_event calls)

    # --- Create pet ---
    if _CREATE_PET_PATTERN.search(message):
        # Extract name if possible (e.g., "叫豆豆" → "豆豆")
        name_match = re.search(r"叫(\S+)", message)
        name = name_match.group(1) if name_match else ""
        if name:
            actions.append(SuggestedAction(
                tool_name="create_pet",
                arguments={"name": name, "species": "dog"},
                confidence=0.7,  # Lower — LLM should refine species/breed
                confirm_description=f"添加新宠物「{name}」",
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
                    if extracted is not None:
                        # We have a concrete value — can be used for confirm card
                        args = {"pet_id": pet_id, "info": {key: extracted}}
                        desc = f"把{pet_name}的{key}改为「{extracted}」"
                    else:
                        # Raw message — need LLM to extract
                        args = {"pet_id": pet_id, "info": {key: message}}
                        desc = f"更新{pet_name}的{key}"
                        conf = min(conf, 0.7)  # Lower confidence since we can't extract value

                    actions.append(SuggestedAction(
                        tool_name="update_pet_profile",
                        arguments=args,
                        confidence=conf,
                        confirm_description=desc,
                    ))
                break

    return actions


def get_confirmable_actions(actions: list[SuggestedAction]) -> list[SuggestedAction]:
    """Return actions suitable for confirm cards (medium confidence + extractable values)."""
    return [
        a for a in actions
        if CONFIRM_THRESHOLD <= a.confidence < 0.8
        and a.confirm_description
    ]


def format_actions_for_prompt(actions: list[SuggestedAction]) -> str:
    """Format high-confidence actions as a system prompt section."""
    high_confidence = [a for a in actions if a.confidence >= 0.8]
    if not high_confidence:
        return ""

    lines = [
        "## Pre-analyzed actions (EXECUTE THESE)",
        "The following actions were detected from the user's message. "
        "You MUST call these tools with these arguments. "
        "You MUST rewrite the title into a short 2-8 word summary (e.g. '学校公园散步', '喂了200克狗粮'). "
        "NEVER use the user's raw sentence as the title. Keep all other fields exactly as shown.",
        "",
    ]
    for i, action in enumerate(high_confidence, 1):
        args_str = ", ".join(f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}"
                             for k, v in action.arguments.items())
        lines.append(f"{i}. {action.tool_name}({args_str})")

    lines.append("")
    if len(high_confidence) > 1:
        lines.append("Execute these actions in the order listed. After each tool call, use the result to inform the next one.")
        lines.append("")
    lines.append("After calling the tool(s), give a brief warm confirmation to the user.")
    return "\n".join(lines)
