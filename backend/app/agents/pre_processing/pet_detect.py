"""Pet creation + profile-update intent detection.

Emits SuggestedActions for create_pet (new pet phrases) and
update_pet_profile (attribute mentions like "weighs 5kg", "allergic to
chicken"). Short-circuits on question-style messages so asking
"is my dog allergic?" doesn't trigger a profile update.
"""

import re

from app.agents.locale import t
from .types import SuggestedAction
from .pet_utils import resolve_pets, extract_gender, extract_birthday, VALUE_EXTRACTORS


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


def detect_create_pet(message: str, lang: str) -> list[SuggestedAction]:
    """Detect pet creation intent and return suggested actions."""
    actions: list[SuggestedAction] = []

    if not _CREATE_PET_PATTERN.search(message):
        return actions

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
    gender = extract_gender(message)
    birthday = extract_birthday(message)

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

    return actions


def detect_update_profile(
    message: str,
    pets: list,
    is_question: bool,
    lang: str,
) -> list[SuggestedAction]:
    """Detect pet profile update intent and return suggested actions."""
    actions: list[SuggestedAction] = []

    if is_question or not pets:
        return actions

    resolved_pets = resolve_pets(message, pets)
    for pattern, key, conf in _UPDATE_PROFILE_PATTERNS:
        if pattern.search(message):
            # Try to extract the actual value
            extractor = VALUE_EXTRACTORS.get(key)
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
