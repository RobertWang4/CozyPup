"""Pet profile tool handlers."""

import asyncio
import base64
import logging
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Pet, Species
from app.agents.tools.registry import register_tool

UPLOAD_DIR = Path("/app/uploads/avatars") if Path("/app/uploads").exists() else Path(__file__).resolve().parent.parent.parent / "uploads" / "avatars"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 聊天上传的图片目录（chat.py 写入，工具读取）
PHOTO_DIR = Path("/app/uploads/photos") if Path("/app/uploads").exists() else Path(__file__).resolve().parent.parent.parent / "uploads" / "photos"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

# Background task tracking — prevents garbage collection of fire-and-forget tasks
_bg_tasks: set[asyncio.Task] = set()

PET_COLORS = ["E8835C", "6BA3BE", "7BAE7F", "9B7ED8", "E8A33C"]

_SPECIES_ZH = {"dog": "狗", "cat": "猫", "other": "其他"}


async def verify_pet_ownership(
    db: AsyncSession, pet_id: str, user_id: uuid.UUID
) -> Pet | None:
    """Verify pet belongs to user. Returns Pet or None."""
    result = await db.execute(
        select(Pet).where(Pet.id == uuid.UUID(pet_id), Pet.user_id == user_id)
    )
    return result.scalar_one_or_none()


def generate_initial_profile_md(
    name: str, species: str, breed: str, birthday: date | None, weight: float | None,
) -> str:
    lines = [f"# {name}", "", "## 基本信息"]
    lines.append(f"- 类型：{_SPECIES_ZH.get(species, species)}")
    if breed:
        lines.append(f"- 品种：{breed}")
    if birthday:
        lines.append(f"- 生日：{birthday.isoformat()}")
    if weight and weight > 0:
        lines.append(f"- 体重：{weight:.1f} kg")
    lines.extend(["", "## 性格", "", "## 健康", "", "## 日常"])
    return "\n".join(lines)


def sync_profile_md(pet) -> str:
    """Regenerate profile_md from pet columns + profile JSON.

    Preserves any LLM-written sections (性格/健康/日常) while syncing
    structured data from profile JSON into the document.
    """
    profile = dict(pet.profile) if pet.profile else {}
    species_zh = _SPECIES_ZH.get(
        pet.species.value if hasattr(pet.species, "value") else str(pet.species),
        str(pet.species),
    )
    gender_map = {"male": "公", "female": "母"}

    # Build 基本信息 section from structured fields
    basics = [f"# {pet.name}", "", "## 基本信息", f"- 类型：{species_zh}"]
    if pet.breed:
        basics.append(f"- 品种：{pet.breed}")
    gender = profile.get("gender")
    if gender:
        basics.append(f"- 性别：{gender_map.get(gender, gender)}")
    if pet.birthday:
        basics.append(f"- 生日：{pet.birthday.isoformat()}")
    if pet.weight and pet.weight > 0:
        basics.append(f"- 体重：{pet.weight:.1f} kg")
    if profile.get("neutered"):
        basics.append("- 已绝育")
    if profile.get("coat_color"):
        basics.append(f"- 毛色：{profile['coat_color']}")

    # Build sections from free-text profile fields
    sections = {}
    FIELD_SECTIONS = {
        "diet": ("日常", "饮食"),
        "allergies": ("健康", "过敏"),
        "vet": ("健康", "兽医"),
        "temperament": ("性格", "性格特点"),
        "medication": ("健康", "用药"),
        "vaccination": ("健康", "疫苗"),
        "vaccines": ("健康", "疫苗"),
        "vaccination_status": ("健康", "疫苗"),
        "deworming": ("健康", "驱虫"),
        "deworming_status": ("健康", "驱虫"),
        "health_notes": ("健康", "健康备注"),
        "routine": ("日常", "日常习惯"),
        "preferences": ("日常", "喜好"),
    }
    for key, (section, label) in FIELD_SECTIONS.items():
        val = profile.get(key)
        if val:
            sections.setdefault(section, []).append(f"- {label}：{val}")

    # Preserve existing LLM-written content from current profile_md
    existing_md = pet.profile_md or ""
    preserved = {}
    current_section = None
    for line in existing_md.split("\n"):
        if line.startswith("## "):
            current_section = line[3:].strip()
        elif current_section and line.strip() and not line.startswith("# "):
            # Don't preserve lines we're about to regenerate
            if current_section not in ("基本信息",):
                preserved.setdefault(current_section, []).append(line)

    # Assemble final document
    lines = basics
    for section_name in ("性格", "健康", "日常"):
        lines.extend(["", f"## {section_name}"])
        # Add structured data first
        if section_name in sections:
            lines.extend(sections[section_name])
        # Then preserved LLM content (skip duplicates)
        if section_name in preserved:
            structured_texts = {l for l in sections.get(section_name, [])}
            for line in preserved[section_name]:
                if line not in structured_texts:
                    lines.append(line)

    return "\n".join(lines)


def sanitize_info(info: dict) -> tuple[dict, list[str]]:
    """Sanitize LLM-provided info values. Returns (cleaned_info, rejected_keys)."""
    rejected = []
    # Short-string fields: max length varies by field
    MAX_LEN = {"breed": 25, "name": 20, "coat_color": 15, "gender": 10}
    for key, max_len in MAX_LEN.items():
        if key in info and isinstance(info[key], str) and len(info[key]) > max_len:
            rejected.append(key)
            del info[key]
    # Weight must be a number
    for wk in ("weight", "weight_kg"):
        if wk in info and not isinstance(info[wk], (int, float)):
            try:
                info[wk] = float(info[wk])
            except (ValueError, TypeError):
                rejected.append(wk)
                del info[wk]
    return info, rejected


def apply_profile_updates(pet, info: dict, existing: dict):
    """Apply standard profile field updates to pet model columns."""
    if "birthday" in info:
        try:
            pet.birthday = date.fromisoformat(str(info["birthday"]))
        except (ValueError, TypeError):
            pass
    if "weight" in info or "weight_kg" in info:
        w = info.get("weight") or info.get("weight_kg")
        if isinstance(w, (int, float)):
            pet.weight = float(w)
    if "name" in info:
        pet.name = str(info["name"])
    if "breed" in info:
        pet.breed = str(info["breed"])


@register_tool("create_pet")
async def create_pet(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Create a new pet profile."""
    name = arguments["name"]
    species = Species(arguments["species"])

    # Check for duplicate pet name
    dup_result = await db.execute(
        select(Pet).where(Pet.user_id == user_id, func.lower(Pet.name) == name.lower())
    )
    existing_pet = dup_result.scalar_one_or_none()
    if existing_pet:
        # Auto-redirect: convert create_pet → update_pet_profile for existing pet
        update_info = {}
        for key in ("gender", "breed", "neutered", "coat_color", "diet", "temperament", "allergies"):
            if key in arguments:
                update_info[key] = arguments[key]
        if "birthday" in arguments:
            update_info["birthday"] = arguments["birthday"]
        if "weight" in arguments:
            update_info["weight"] = arguments["weight"]
        if update_info:
            return await update_pet_profile(
                {"pet_id": str(existing_pet.id), "info": update_info}, db, user_id
            )
        return {
            "success": True,
            "message": f"宠物「{name}」已存在，无需重复创建。",
            "card": {"type": "pet_updated", "pet_id": str(existing_pet.id), "name": name},
        }
    breed = arguments.get("breed", "")
    birthday_str = arguments.get("birthday")
    weight = arguments.get("weight")

    # Auto-assign color
    count_result = await db.execute(
        select(func.count()).where(Pet.user_id == user_id)
    )
    count = count_result.scalar() or 0
    color = PET_COLORS[count % len(PET_COLORS)]

    bday = date.fromisoformat(birthday_str) if birthday_str else None
    pet = Pet(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        species=species,
        breed=breed,
        birthday=bday,
        weight=weight,
        color_hex=color,
        profile_md=generate_initial_profile_md(name, arguments["species"], breed, bday, weight),
    )

    # Lock species on creation (always required)
    pet.species_locked = True

    # Store optional fields in flexible profile JSON
    profile = {}
    for key in ("gender", "neutered", "coat_color"):
        if key in arguments:
            profile[key] = arguments[key]
    # Lock gender if provided at creation
    if "gender" in arguments:
        profile["gender_locked"] = True
    if profile:
        pet.profile = profile

    db.add(pet)
    await db.flush()

    card = {
        "type": "pet_created",
        "pet_id": str(pet.id),
        "pet_name": name,
        "species": arguments["species"],
        "breed": breed,
    }

    return {
        "success": True,
        "pet_id": str(pet.id),
        "pet_name": name,
        "species": arguments["species"],
        "card": card,
    }


@register_tool("update_pet_profile")
async def update_pet_profile(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Merge new info into the pet's flexible JSON profile."""
    pet_id = uuid.UUID(arguments["pet_id"])
    info = arguments.get("info", {})
    force_lock = arguments.pop("_force_lock", False)
    if not info:
        return {"success": False, "error": "No info provided"}

    result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        return {"success": False, "error": "Pet not found"}

    # --- Sanitize LLM values (reject raw sentences in short fields) ---
    info, rejected_keys = sanitize_info(info)
    if not info and rejected_keys:
        return {
            "success": False,
            "error": f"Invalid values for: {', '.join(rejected_keys)}. "
                     "Breed, name, coat_color should be short values, not full sentences.",
        }

    # --- Force-lock path: user confirmed via confirm card ---
    existing = dict(pet.profile) if pet.profile else {}

    if force_lock:
        if "gender" in info:
            existing["gender"] = info["gender"]
            existing["gender_locked"] = True
        if "species" in info:
            pet.species = Species(info["species"])
            pet.species_locked = True
        existing.update(info)
        pet.profile = existing
        pet.profile_md = sync_profile_md(pet)
        await db.flush()
        return {
            "success": True,
            "pet_id": str(pet.id),
            "pet_name": pet.name,
            "saved_keys": list(info.keys()),
            "card": {
                "type": "pet_updated",
                "pet_id": str(pet.id),
                "pet_name": pet.name,
                "saved_keys": list(info.keys()),
            },
        }

    # --- Check locked fields (gender / species) ---
    rejected: list[str] = []

    if "gender" in info and existing.get("gender_locked"):
        rejected.append("gender")
        del info["gender"]
    if "species" in info and pet.species_locked:
        rejected.append("species")
        del info["species"]

    if rejected and not info:
        label = "、".join("性别" if f == "gender" else "物种" for f in rejected)
        return {
            "success": False,
            "error": f"{pet.name}的{label}已经设定过了，无法修改。",
        }

    # --- Gender/species first-time set → needs confirm card ---
    setting_gender = "gender" in info and not existing.get("gender_locked")
    setting_species = "species" in info and not pet.species_locked

    if setting_gender or setting_species:
        # Separate lockable fields from normal fields
        lockable = {}
        if setting_gender:
            lockable["gender"] = info.pop("gender")
        if setting_species:
            lockable["species"] = info.pop("species")

        # Execute remaining normal fields immediately
        if info:
            apply_profile_updates(pet, info, existing)
            existing.update(info)
            pet.profile = existing
            await db.flush()

        # Build confirm description
        parts = []
        gender_map = {"male": "公", "female": "母"}
        species_map = {"dog": "狗", "cat": "猫", "other": "其他"}
        if "gender" in lockable:
            g = gender_map.get(lockable["gender"], lockable["gender"])
            parts.append(f"性别设为「{g}」")
        if "species" in lockable:
            s = species_map.get(lockable["species"], lockable["species"])
            parts.append(f"物种设为「{s}」")
        desc = f"{pet.name}: {'，'.join(parts)}（⚠️ 一旦确认将无法修改）"

        return {
            "success": True,
            "needs_confirm": True,
            "pet_id": str(pet.id),
            "pet_name": pet.name,
            "confirm_tool": "update_pet_profile",
            "confirm_arguments": {"pet_id": str(pet.id), "info": lockable, "_force_lock": True},
            "confirm_description": desc,
            "saved_keys": list(info.keys()) if info else [],
        }

    # --- Normal update (no lockable fields) ---
    apply_profile_updates(pet, info, existing)
    existing.update(info)
    pet.profile = existing

    # Auto-sync profile_md from structured data
    pet.profile_md = sync_profile_md(pet)

    await db.flush()

    card = {
        "type": "pet_updated",
        "pet_name": pet.name,
        "saved_keys": list(info.keys()),
    }

    return {
        "success": True,
        "pet_id": str(pet.id),
        "pet_name": pet.name,
        "saved_keys": list(info.keys()),
        "card": card,
    }


@register_tool("save_pet_profile_md")
async def save_pet_profile_md(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Save the pet's narrative markdown profile."""
    pet_id = uuid.UUID(arguments["pet_id"])
    profile_md = arguments.get("profile_md", "").strip()
    if not profile_md:
        return {"success": False, "error": "Empty profile_md"}
    if len(profile_md) > 3000:
        return {"success": False, "error": "profile_md too long (max 3000 chars)"}

    result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        return {"success": False, "error": "Pet not found"}

    pet.profile_md = profile_md
    await db.flush()

    return {"success": True, "pet_id": str(pet.id), "pet_name": pet.name}


@register_tool("summarize_pet_profile")
async def summarize_pet_profile(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """User-triggered: summarize and update the pet's profile document."""
    pet_id = uuid.UUID(arguments["pet_id"])
    profile_md = arguments.get("profile_md", "").strip()
    if not profile_md:
        return {"success": False, "error": "Empty profile_md"}
    if len(profile_md) > 5000:
        return {"success": False, "error": "profile_md too long (max 5000 chars)"}

    result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        return {"success": False, "error": "Pet not found"}

    pet.profile_md = profile_md
    await db.flush()

    card = {
        "type": "profile_summarized",
        "pet_name": pet.name,
    }

    return {
        "success": True,
        "pet_id": str(pet.id),
        "pet_name": pet.name,
        "card": card,
    }


@register_tool("list_pets")
async def list_pets(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """List all pets for the user."""
    result = await db.execute(
        select(Pet).where(Pet.user_id == user_id).order_by(Pet.created_at)
    )
    pets = result.scalars().all()

    return {
        "pets": [
            {
                "id": str(p.id),
                "name": p.name,
                "species": p.species.value,
                "breed": p.breed,
                "birthday": p.birthday.isoformat() if p.birthday else None,
                "weight": p.weight,
                "profile": p.profile or {},
            }
            for p in pets
        ],
        "count": len(pets),
    }


@register_tool("delete_pet")
async def delete_pet(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Delete a pet profile."""
    pet_id = uuid.UUID(arguments["pet_id"])

    result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        return {"success": False, "error": "Pet not found"}

    pet_name = pet.name
    await db.delete(pet)
    await db.flush()

    return {
        "success": True,
        "pet_id": str(pet_id),
        "pet_name": pet_name,
        "card": {
            "type": "pet_deleted",
            "pet_name": pet_name,
        },
    }


@register_tool("set_pet_avatar", accepts_kwargs=True)
async def set_pet_avatar(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    **kwargs,
) -> dict:
    """Set a pet's avatar. Uses already-saved image_urls from chat flow."""
    pet_id = uuid.UUID(arguments["pet_id"])

    result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        return {"success": False, "error": "Pet not found"}

    # Priority:
    # 1) image_urls — 聊天流已存好的图片 URL（最优，不需要重新 decode）
    # 2) photo_url — LLM 指定之前上传的图片路径
    # 3) images (raw base64) — 兜底
    image_urls = kwargs.get("image_urls") or []
    photo_url = arguments.get("photo_url")
    image_data: bytes | None = None

    if image_urls:
        # 直接从已保存的文件读取（避免重新 decode base64）
        filename = image_urls[0].split("/")[-1]
        filepath = PHOTO_DIR / filename
        if filepath.exists():
            image_data = filepath.read_bytes()
    elif photo_url:
        # LLM 引用了之前对话中的图片路径
        filename = photo_url.split("/")[-1]
        filepath = PHOTO_DIR / filename
        if filepath.exists():
            image_data = filepath.read_bytes()
    else:
        # 兜底：raw base64（不应该走到这里，但保持兼容）
        images = kwargs.get("images")
        if images:
            image_data = base64.b64decode(images[0])

    logger.info("set_pet_avatar_debug", extra={
        "pet_id": str(pet_id),
        "source": "image_urls" if image_urls else ("photo_url" if photo_url else "base64_fallback"),
        "image_data_len": len(image_data) if image_data else 0,
    })
    if not image_data:
        return {"success": False, "error": "No image provided. Ask the user to attach a photo."}
    if len(image_data) > 5 * 1024 * 1024:
        return {"success": False, "error": "Image must be under 5MB"}

    # Upload to GCS if configured, otherwise local
    from app.config import settings
    if settings.gcs_bucket:
        from app.storage import upload_avatar as gcs_upload_avatar
        gcs_upload_avatar(str(pet_id), image_data, "image/jpeg")
    else:
        filename = f"{pet_id}.jpg"
        filepath = UPLOAD_DIR / filename
        filepath.write_bytes(image_data)
    # Always use relative URL — iOS avatarURL() builds the full URL from this
    avatar_url = f"/api/v1/pets/{pet_id}/avatar"
    logger.info("avatar_file_written", extra={"pet_id": str(pet_id), "gcs": bool(settings.gcs_bucket), "size": len(image_data)})

    pet.avatar_url = avatar_url
    await db.flush()

    return {
        "success": True,
        "pet_id": str(pet_id),
        "pet_name": pet.name,
        "avatar_url": pet.avatar_url,
        "card": {
            "type": "pet_updated",
            "pet_id": str(pet.id),
            "pet_name": pet.name,
            "saved_keys": ["avatar"],
        },
    }
