"""Pet name resolution and value extraction utilities for pre-processing."""

import re
from datetime import date


def resolve_pets(message: str, pets: list) -> list[tuple[str, str]]:
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


def extract_new_name(message: str) -> str | None:
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


def extract_weight(message: str) -> float | None:
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


def extract_birthday(message: str) -> str | None:
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


def extract_gender(message: str) -> str | None:
    """Extract gender from message."""
    if re.search(r"公的|公狗|公猫|male|boy|男", message, re.I):
        return "male"
    if re.search(r"母的|母狗|母猫|female|girl|女", message, re.I):
        return "female"
    return None


# Value extractors by key — returns extracted value or None
VALUE_EXTRACTORS: dict[str, callable] = {
    "name": extract_new_name,
    "birthday": extract_birthday,
    "weight": extract_weight,
    "gender": extract_gender,
}
