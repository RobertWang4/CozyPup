"""Structured display details for confirmation cards."""

from __future__ import annotations


def confirm_card_details(fn_name: str, fn_args: dict, lang: str) -> dict:
    """Return optional structured fields for richer confirm cards."""
    if fn_name == "create_pet":
        labels = {
            "name": "名字" if lang == "zh" else "Name",
            "gender": "性别" if lang == "zh" else "Gender",
            "breed": "品种" if lang == "zh" else "Breed",
            "species": "类型" if lang == "zh" else "Type",
        }
        species_label = {
            "dog": "狗" if lang == "zh" else "Dog",
            "cat": "猫" if lang == "zh" else "Cat",
            "other": "其他" if lang == "zh" else "Other",
        }
        gender_label = {
            "male": "公" if lang == "zh" else "Male",
            "female": "母" if lang == "zh" else "Female",
            "unknown": "未知" if lang == "zh" else "Unknown",
        }
        fields = []
        if fn_args.get("name"):
            fields.append({"label": labels["name"], "value": str(fn_args["name"])})
        if fn_args.get("gender"):
            gender = str(fn_args["gender"])
            fields.append({"label": labels["gender"], "value": gender_label.get(gender, gender)})
        if fn_args.get("breed"):
            fields.append({"label": labels["breed"], "value": str(fn_args["breed"])})
        elif fn_args.get("species"):
            species = str(fn_args["species"])
            fields.append({"label": labels["species"], "value": species_label.get(species, species)})
        return {
            "title": "新增宠物确认" if lang == "zh" else "Confirm New Pet",
            "action_kind": "create_pet",
            "fields": fields,
        }

    if fn_name == "update_pet_profile":
        info = fn_args.get("info") or {}
        from app.agents.tools.pets import _format_saved_fields
        return {
            "title": "修改宠物确认" if lang == "zh" else "Confirm Pet Changes",
            "action_kind": "update_pet_profile",
            "fields": [
                {"label": item["label"], "value": item["value"]}
                for item in _format_saved_fields(info, lang)
            ],
        }

    return {}
