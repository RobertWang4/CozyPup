"""Deterministic pre-processor — extracts intent and pre-fills tool arguments
before the LLM sees the message.

When confidence is high, the suggested actions are injected into the system
prompt so the LLM only needs to copy-paste the arguments into a tool call.
If the LLM still fails, the post-processor can execute these directly.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class SuggestedAction:
    tool_name: str
    arguments: dict
    confidence: float  # 0.0 - 1.0


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
    (re.compile(r"生日[是在]|birthday", re.I), "birthday"),
    (re.compile(r"体重[是有]?|重.*?(?:斤|kg|公斤)|weigh", re.I), "weight"),
    (re.compile(r"过敏|allerg", re.I), "allergies"),
    (re.compile(r"是公的|是母的|公狗|母狗|male|female|gender|性别", re.I), "gender"),
    (re.compile(r"绝育|neutered|spayed", re.I), "neutered"),
]


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
                        confidence=confidence,
                    ))
                break  # Only match first category

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
            ))

    # --- Update pet profile ---
    if not is_question and pets:
        resolved_pets = _resolve_pets(message, pets)
        for pattern, key in _UPDATE_PROFILE_PATTERNS:
            if pattern.search(message):
                for pet_id, _ in resolved_pets:
                    actions.append(SuggestedAction(
                        tool_name="update_pet_profile",
                        arguments={"pet_id": pet_id, "info": {key: message}},
                        confidence=0.7,  # LLM should extract the actual value
                    ))
                break

    return actions


def format_actions_for_prompt(actions: list[SuggestedAction]) -> str:
    """Format high-confidence actions as a system prompt section."""
    high_confidence = [a for a in actions if a.confidence >= 0.8]
    if not high_confidence:
        return ""

    lines = [
        "## Pre-analyzed actions (EXECUTE THESE)",
        "The following actions were detected from the user's message. "
        "You MUST call these tools with these arguments. "
        "You may adjust the title to be more concise, but keep all other fields exactly as shown.",
        "",
    ]
    for i, action in enumerate(high_confidence, 1):
        args_str = ", ".join(f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}"
                             for k, v in action.arguments.items())
        lines.append(f"{i}. {action.tool_name}({args_str})")

    lines.append("")
    lines.append("After calling the tool(s), give a brief warm confirmation to the user.")
    return "\n".join(lines)
