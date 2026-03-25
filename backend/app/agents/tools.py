"""LiteLLM-compatible tool definitions and execution logic for the Chat Agent."""

import asyncio
import base64
import json
import logging
import uuid
from datetime import date, datetime, time
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CalendarEvent, EventCategory, EventSource, EventType,
    Pet, Reminder, Species,
)

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads" / "avatars"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

PHOTO_DIR = Path(__file__).resolve().parent.parent / "uploads" / "photos"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

# Background task tracking — prevents garbage collection of fire-and-forget tasks
_bg_tasks: set[asyncio.Task] = set()

# ---------- Tool Definitions (OpenAI function calling format) ----------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": (
                "记录宠物已发生的健康/生活事件。\n"
                "当用户报告已经发生的事情时使用 (吃了/拉了/打了疫苗/遛了/洗澡了)。\n"
                "对于所有宠物或主人共有的事件 (买狗粮/逛宠物店)，只调用一次且不传 pet_id。\n"
                "不要用于: 用户询问过去的事 (用 query_calendar_events)。\n"
                "不要用于: 用户想设未来提醒 (用 create_reminder)。\n"
                "不要用于: 紧急症状 (用 trigger_emergency)。\n"
                "title 必须是 2-8 字摘要，不要用原始句子。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of a single pet. Use pet_ids for multi-pet events.",
                    },
                    "pet_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of pet UUIDs this event applies to. Use for multi-pet events "
                            "(e.g. both dogs went for a walk). OMIT for owner-only events. "
                            "If only one pet, you can use pet_id instead."
                        ),
                    },
                    "event_date": {
                        "type": "string",
                        "description": "Date of the event in YYYY-MM-DD format.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Short description of the event, e.g. 'Fed 200g kibble' or 'Vomited twice'.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"],
                        "description": "Category of the health event.",
                    },
                    "event_time": {
                        "type": "string",
                        "description": "Optional time in HH:MM format.",
                    },
                    "raw_text": {
                        "type": "string",
                        "description": "Optional original user text that triggered this record.",
                    },
                    "photo_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "URLs of photos to attach to this event (if user sent images)",
                    },
                },
                "required": ["event_date", "title", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_calendar_events",
            "description": (
                "查询宠物的历史事件记录。\n"
                "当用户询问过去发生的事情时使用 (上次打疫苗是什么时候？最近吃了什么？)。\n"
                "不要用于: 记录新发生的事 (用 create_calendar_event)。\n"
                "不要用于: 查看提醒 (用 list_reminders)。\n"
                "可按 pet_id、日期范围、category 过滤。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "Optional UUID of the pet to filter by.",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Optional start date in YYYY-MM-DD format.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Optional end date in YYYY-MM-DD format.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"],
                        "description": "Optional category filter.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_calendar_event",
            "description": (
                "修改已有的日历事件。\n"
                "当用户想更正/修改之前记录的事件时使用 (日期写错了/标题要改)。\n"
                "不要用于: 记录新事件 (用 create_calendar_event)。\n"
                "必须先调 query_calendar_events 获取 event_id。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "UUID of the event to update (from query_calendar_events results).",
                    },
                    "event_date": {
                        "type": "string",
                        "description": "New date in YYYY-MM-DD format.",
                    },
                    "event_time": {
                        "type": "string",
                        "description": "New time in HH:MM format.",
                    },
                    "title": {
                        "type": "string",
                        "description": "New title/description.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"],
                        "description": "New category.",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_pet",
            "description": (
                "为用户创建新的宠物档案。\n"
                "当用户说有新宠物要添加时使用 (我养了一只猫/我新买了一只狗)。\n"
                "不要用于: 更新已有宠物信息 (用 update_pet_profile)。\n"
                "不要用于: 改名 (用 update_pet_profile 传 name)。\n"
                "至少需要 name 和 species。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The pet's name."},
                    "species": {"type": "string", "enum": ["dog", "cat", "other"], "description": "The type of animal."},
                    "breed": {"type": "string", "description": "Breed, e.g. 'Golden Retriever'. Empty string if unknown."},
                    "birthday": {"type": "string", "description": "Optional birthday in YYYY-MM-DD format."},
                    "weight": {"type": "number", "description": "Optional weight in kg."},
                    "gender": {"type": "string", "enum": ["male", "female", "unknown"], "description": "Optional gender."},
                    "neutered": {"type": "boolean", "description": "Optional neutered/spayed status."},
                    "coat_color": {"type": "string", "description": "Optional coat color."},
                },
                "required": ["name", "species"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_pet_profile",
            "description": (
                "更新宠物档案信息，包括改名。\n"
                "当用户提到宠物的任何属性时使用 (体重/生日/过敏/品种/性别/饮食/性格/兽医等)。\n"
                "改名: 在 info 里传 {\"name\": \"新名字\"}。\n"
                "不要用于: 添加新宠物 (用 create_pet)。\n"
                "不要用于: 记录事件 (用 create_calendar_event)。\n"
                "主动调用以逐步完善宠物画像。info 是灵活的 key-value 对。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet.",
                    },
                    "info": {
                        "type": "object",
                        "description": (
                            "Key-value pairs of pet info to save. Any keys are allowed. "
                            "Examples: {\"gender\": \"male\", \"weight_kg\": 5.2, \"allergies\": [\"chicken\"], "
                            "\"diet\": \"Royal Canin 200g 2x/day\", \"neutered\": true, \"vet\": \"瑞鹏医院\", "
                            "\"temperament\": \"friendly but anxious\", \"coat_color\": \"golden\"}"
                        ),
                    },
                },
                "required": ["pet_id", "info"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_pet_profile_md",
            "description": (
                "保存/更新宠物的叙事性档案文档 (markdown)。\n"
                "当从对话中了解到宠物新信息时静默调用 (性格/病史/日常习惯/偏好)。\n"
                "不要用于: 更新结构化字段如体重/生日 (用 update_pet_profile)。\n"
                "必须传完整文档 (非 diff)，500 字以内，用 markdown 分节。\n"
                "用用户的语言撰写。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet.",
                    },
                    "profile_md": {
                        "type": "string",
                        "description": (
                            "The FULL markdown profile document. Include all previously known info "
                            "plus new info. Sections: basics, personality, health, daily routine."
                        ),
                    },
                },
                "required": ["pet_id", "profile_md"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_pet_profile",
            "description": (
                "用户主动要求总结/更新宠物档案时调用。\n"
                "回顾所有已知信息和聊天历史，生成完整的宠物档案文档。\n"
                "仅在用户明确要求时调用 (帮我总结一下XX的信息/更新一下档案/整理一下宠物资料)。\n"
                "必须传完整文档 (非 diff)，800 字以内，用 markdown 分节。\n"
                "用用户的语言撰写，尽量丰富详实。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet.",
                    },
                    "profile_md": {
                        "type": "string",
                        "description": (
                            "The FULL markdown profile document. Summarize ALL known info about the pet "
                            "from conversation history and existing profile. Sections: basics, personality, "
                            "health, daily routine, notes. Be thorough and detailed."
                        ),
                    },
                },
                "required": ["pet_id", "profile_md"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pets",
            "description": (
                "列出用户所有已注册的宠物及其档案。\n"
                "当用户问自己有哪些宠物、或你需要查 pet_id 时使用。\n"
                "不要用于: 创建新宠物 (用 create_pet)。\n"
                "无参数，返回全部宠物列表。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": (
                "创建一个定时推送提醒。\n"
                "当用户要求未来某时提醒他做某事时使用 (明天提醒我喂药/下周二带去打疫苗)。\n"
                "不要用于: 记录已发生的事 (用 create_calendar_event)。\n"
                "不要用于: 查看已有提醒 (用 list_reminders)。\n"
                "trigger_at 必须是未来时间，ISO 8601 格式。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet this reminder is for.",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["medication", "vaccine", "checkup", "feeding", "grooming", "other"],
                        "description": "Type of reminder.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Short reminder title, e.g. 'Give heartworm medication'.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional detailed description.",
                    },
                    "trigger_at": {
                        "type": "string",
                        "description": "When to send the reminder, in ISO 8601 format (YYYY-MM-DDTHH:MM:SS).",
                    },
                },
                "required": ["pet_id", "type", "title", "trigger_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_places",
            "description": (
                "搜索附近的宠物相关地点 (宠物医院/宠物店/狗公园/美容店/24h急诊)。\n"
                "当用户问附近哪里有…/帮我找…时使用。\n"
                "不要用于: 记录去过的地方 (用 create_calendar_event)。\n"
                "需要用户授权位置信息才能使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search query for Google Places, e.g. 'veterinary clinic', "
                            "'dog park', '24 hour emergency vet'."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_email",
            "description": (
                "生成邮件草稿卡片供用户审阅和发送。\n"
                "当用户要写邮件给兽医或宠物服务商时使用。\n"
                "不要用于: 聊天回复 (直接回复即可)。\n"
                "你来根据对话上下文撰写邮件内容，然后调用此工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "Email subject line.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Full email body text.",
                    },
                },
                "required": ["subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_pet",
            "description": (
                "删除宠物档案。\n"
                "当用户明确要求移除某个宠物时使用。\n"
                "不要用于: 更新宠物信息 (用 update_pet_profile)。\n"
                "此操作不可逆，需确认用户意图。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet to delete.",
                    },
                },
                "required": ["pet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event",
            "description": (
                "删除日历事件记录。\n"
                "当用户要求删除之前记录的事件时使用。\n"
                "不要用于: 修改事件 (用 update_calendar_event)。\n"
                "必须先调 query_calendar_events 获取 event_id。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "UUID of the event to delete (from query_calendar_events results).",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": (
                "列出用户所有未发送的提醒。\n"
                "当用户问有哪些提醒/定时任务时使用。\n"
                "不要用于: 查看历史事件 (用 query_calendar_events)。\n"
                "无参数，返回全部活跃提醒。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_reminder",
            "description": (
                "修改已有的提醒。\n"
                "当用户要改提醒的时间/标题/内容时使用。\n"
                "不要用于: 创建新提醒 (用 create_reminder)。\n"
                "必须先调 list_reminders 获取 reminder_id。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {
                        "type": "string",
                        "description": "UUID of the reminder to update (from list_reminders results).",
                    },
                    "title": {
                        "type": "string",
                        "description": "New reminder title.",
                    },
                    "body": {
                        "type": "string",
                        "description": "New reminder body/description.",
                    },
                    "trigger_at": {
                        "type": "string",
                        "description": "New trigger time in ISO 8601 format (YYYY-MM-DDTHH:MM:SS).",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["medication", "vaccine", "checkup", "feeding", "grooming", "other"],
                        "description": "New reminder type.",
                    },
                },
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_reminder",
            "description": (
                "删除/取消一个提醒。\n"
                "当用户要取消已设定的提醒时使用。\n"
                "不要用于: 修改提醒 (用 update_reminder)。\n"
                "必须先调 list_reminders 获取 reminder_id。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {
                        "type": "string",
                        "description": "UUID of the reminder to delete (from list_reminders results).",
                    },
                },
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upload_event_photo",
            "description": (
                "将用户的照片附加到日历事件。\n"
                "当用户发了照片并要求关联到某条记录时使用。\n"
                "不要用于: 设置宠物头像 (用 set_pet_avatar)。\n"
                "照片自动从用户消息中获取，需要先有 event_id。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "UUID of the event to attach the photo to.",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_language",
            "description": (
                "切换应用显示语言。\n"
                "当用户要求切换语言时使用 (说英文/switch to English)。\n"
                "不要用于: 翻译内容 (直接用目标语言回复)。\n"
                "支持 zh 和 en。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "enum": ["zh", "en"],
                        "description": "Language code to switch to.",
                    },
                },
                "required": ["language"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_pet_avatar",
            "description": (
                "设置宠物头像。\n"
                "当用户发了照片并说要用作宠物头像时使用。\n"
                "不要用于: 给事件附加照片 (用 upload_event_photo)。\n"
                "照片自动从用户消息中获取。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet.",
                    },
                },
                "required": ["pet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_emergency",
            "description": (
                "当判断用户描述的是真正的宠物紧急情况时调用。\n"
                "使用场景: 宠物中毒、抽搐、大出血、呼吸困难、昏迷等危及生命的状况。\n"
                "不要用于: 用户询问过去的紧急事件、一般性健康咨询、轻微不适。\n"
                "调用前请仔细判断是否真的紧急。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "给用户的紧急提示消息",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["find_er", "call_vet", "first_aid"],
                        "description": "建议的紧急操作类型",
                    },
                },
                "required": ["message", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_images",
            "description": (
                "请求查看用户附带的图片。\n"
                "当你需要看图片内容才能回答用户问题时调用（什么颜色/什么品种/图片里是什么）。\n"
                "不要用于: 换头像、存日记等操作（那些工具会自动接收图片，不需要你先看）。\n"
                "调用后图片会返回给你，你再根据图片内容回答用户。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "为什么需要看图片，例如'用户问宠物颜色'",
                    },
                },
                "required": ["reason"],
            },
        },
    },
]


# ---------- Tool Execution ----------


async def _create_calendar_event(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    images: list[str] | None = None,
    **kwargs,
) -> dict:
    """Create a CalendarEvent record in the database."""
    # Resolve pet(s): support both pet_id (single) and pet_ids (multi)
    raw_pet_ids = arguments.get("pet_ids") or []
    if not raw_pet_ids and arguments.get("pet_id"):
        raw_pet_ids = [arguments["pet_id"]]
    pet_ids_str = [str(pid) for pid in raw_pet_ids]

    event_date = date.fromisoformat(arguments["event_date"])
    title = arguments["title"]
    category = EventCategory(arguments["category"])
    event_time_str = arguments.get("event_time")
    raw_text = arguments.get("raw_text", "")

    event_time = None
    if event_time_str:
        parts = event_time_str.split(":")
        event_time = time(int(parts[0]), int(parts[1]))

    # Verify pets belong to user and collect names
    pet_names: list[str] = []
    first_pet_id = None
    if pet_ids_str:
        for pid_str in pet_ids_str:
            pid = uuid.UUID(pid_str)
            result = await db.execute(select(Pet).where(Pet.id == pid, Pet.user_id == user_id))
            pet = result.scalar_one_or_none()
            if pet:
                pet_names.append(pet.name)
                if first_pet_id is None:
                    first_pet_id = pid

    event = CalendarEvent(
        user_id=user_id,
        pet_id=first_pet_id,  # backward compat
        pet_ids=pet_ids_str,
        event_date=event_date,
        event_time=event_time,
        title=title,
        type=EventType.log,
        category=category,
        raw_text=raw_text,
        source=EventSource.chat,
        edited=False,
    )

    # Attach photos: from arguments (LLM-provided URLs) or from user's chat images (base64)
    photo_urls = arguments.get("photo_urls", [])
    if not photo_urls and images:
        # Auto-save base64 images from chat to disk
        for img_b64 in images:
            try:
                image_data = base64.b64decode(img_b64)
                if len(image_data) > 5 * 1024 * 1024:
                    continue
                photo_id = uuid.uuid4()
                filename = f"{photo_id}.jpg"
                filepath = PHOTO_DIR / filename
                filepath.write_bytes(image_data)
                photo_urls.append(f"/api/v1/calendar/photos/{filename}")
            except Exception:
                continue
    if photo_urls:
        event.photos = photo_urls

    db.add(event)
    await db.flush()

    card = {
        "type": "record",
        "pet_name": ", ".join(pet_names) if pet_names else "",
        "date": arguments["event_date"],
        "category": arguments["category"],
        "title": title,
    }

    return {
        "success": True,
        "event_id": str(event.id),
        "title": title,
        "category": arguments["category"],
        "event_date": arguments["event_date"],
        "card": card,
    }


async def _query_calendar_events(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Query CalendarEvent records from the database."""
    query = select(CalendarEvent).where(CalendarEvent.user_id == user_id)

    if arguments.get("pet_id"):
        query = query.where(CalendarEvent.pet_id == uuid.UUID(arguments["pet_id"]))
    if arguments.get("start_date"):
        query = query.where(CalendarEvent.event_date >= date.fromisoformat(arguments["start_date"]))
    if arguments.get("end_date"):
        query = query.where(CalendarEvent.event_date <= date.fromisoformat(arguments["end_date"]))
    if arguments.get("category"):
        query = query.where(CalendarEvent.category == EventCategory(arguments["category"]))

    query = query.order_by(CalendarEvent.event_date.desc()).limit(50)
    result = await db.execute(query)
    events = result.scalars().all()

    return {
        "events": [
            {
                "id": str(e.id),
                "pet_id": str(e.pet_id),
                "event_date": e.event_date.isoformat(),
                "event_time": e.event_time.isoformat() if e.event_time else None,
                "title": e.title,
                "category": e.category.value,
                "raw_text": e.raw_text,
                "source": e.source.value,
            }
            for e in events
        ],
        "count": len(events),
    }


async def _update_calendar_event(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Update an existing CalendarEvent."""
    event_id = uuid.UUID(arguments["event_id"])

    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id, CalendarEvent.user_id == user_id
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        return {"success": False, "error": "Event not found"}

    if "event_date" in arguments:
        event.event_date = date.fromisoformat(arguments["event_date"])
    if "event_time" in arguments:
        parts = arguments["event_time"].split(":")
        event.event_time = time(int(parts[0]), int(parts[1]))
    if "title" in arguments:
        event.title = arguments["title"]
    if "category" in arguments:
        event.category = EventCategory(arguments["category"])

    event.edited = True
    await db.flush()

    # Load pet name for card
    pet_result = await db.execute(select(Pet).where(Pet.id == event.pet_id))
    pet = pet_result.scalar_one_or_none()

    card = {
        "type": "record",
        "pet_name": pet.name if pet else "Unknown",
        "date": event.event_date.isoformat(),
        "category": event.category.value,
        "title": event.title,
    }

    return {
        "success": True,
        "event_id": str(event.id),
        "title": event.title,
        "event_date": event.event_date.isoformat(),
        "card": card,
    }


PET_COLORS = ["E8835C", "6BA3BE", "7BAE7F", "9B7ED8", "E8A33C"]


_SPECIES_ZH = {"dog": "狗", "cat": "猫", "other": "其他"}


def _generate_initial_profile_md(
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


async def _create_pet(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Create a new pet profile."""
    name = arguments["name"]
    species = Species(arguments["species"])
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
        profile_md=_generate_initial_profile_md(name, arguments["species"], breed, bday, weight),
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


async def _update_pet_profile(
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
    info, rejected_keys = _sanitize_info(info)
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
            _apply_profile_updates(pet, info, existing)
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
    _apply_profile_updates(pet, info, existing)
    existing.update(info)
    pet.profile = existing

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


def _sanitize_info(info: dict) -> tuple[dict, list[str]]:
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


def _apply_profile_updates(pet, info: dict, existing: dict):
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


async def _save_pet_profile_md(
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


async def _summarize_pet_profile(
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


async def _list_pets(
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


async def _create_reminder(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Create a reminder for push notification."""
    pet_id = uuid.UUID(arguments["pet_id"])

    # Verify pet belongs to user
    pet_result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = pet_result.scalar_one_or_none()
    if not pet:
        return {"success": False, "error": "Pet not found"}

    reminder = Reminder(
        id=uuid.uuid4(),
        user_id=user_id,
        pet_id=pet_id,
        type=arguments["type"],
        title=arguments["title"],
        body=arguments.get("body", ""),
        trigger_at=datetime.fromisoformat(arguments["trigger_at"]),
    )
    db.add(reminder)
    await db.flush()

    card = {
        "type": "reminder",
        "pet_name": pet.name,
        "title": arguments["title"],
        "trigger_at": arguments["trigger_at"],
        "reminder_type": arguments["type"],
    }

    return {
        "success": True,
        "reminder_id": str(reminder.id),
        "title": arguments["title"],
        "trigger_at": arguments["trigger_at"],
        "card": card,
    }


async def _search_places(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    location: dict | None = None,
    **_kwargs,
) -> dict:
    """Search for nearby places via Google Places API."""
    if not location or "lat" not in location or "lng" not in location:
        return {
            "success": False,
            "error": "No location available. Ask the user to share their location.",
        }

    from app.services.places import places_service  # lazy import

    query = arguments["query"]
    places = await places_service.search_nearby(
        lat=location["lat"], lng=location["lng"], query=query
    )

    if not places:
        return {
            "success": True,
            "places": [],
            "message": f"No results found for '{query}' nearby.",
        }

    card = {
        "type": "map",
        "query": query,
        "places": [
            {
                "name": p["name"],
                "address": p["address"],
                "rating": p.get("rating"),
                "lat": p["lat"],
                "lng": p["lng"],
            }
            for p in places
        ],
    }

    return {
        "success": True,
        "places_count": len(places),
        "top_results": [f"{p['name']} — {p['address']}" for p in places[:5]],
        "card": card,
    }


async def _draft_email(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Wrap an email draft into a card for the frontend."""
    subject = arguments["subject"]
    body = arguments["body"]

    card = {
        "type": "email",
        "subject": subject,
        "body": body,
    }

    return {
        "success": True,
        "card": card,
    }


async def _delete_pet(
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


async def _delete_calendar_event(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Delete a calendar event record."""
    event_id = uuid.UUID(arguments["event_id"])

    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id, CalendarEvent.user_id == user_id
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        return {"success": False, "error": "Event not found"}

    title = event.title
    await db.delete(event)
    await db.flush()

    return {
        "success": True,
        "event_id": str(event_id),
        "title": title,
        "card": {
            "type": "event_deleted",
            "title": title,
        },
    }


async def _list_reminders(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """List the user's active (unsent) reminders."""
    result = await db.execute(
        select(Reminder)
        .where(Reminder.user_id == user_id, Reminder.sent == False)  # noqa: E712
        .order_by(Reminder.trigger_at)
    )
    reminders = result.scalars().all()

    return {
        "reminders": [
            {
                "id": str(r.id),
                "pet_id": str(r.pet_id),
                "type": r.type,
                "title": r.title,
                "body": r.body,
                "trigger_at": r.trigger_at.isoformat() if r.trigger_at else None,
            }
            for r in reminders
        ],
        "count": len(reminders),
    }


async def _update_reminder(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Update an existing reminder."""
    reminder_id = uuid.UUID(arguments["reminder_id"])

    result = await db.execute(
        select(Reminder).where(
            Reminder.id == reminder_id, Reminder.user_id == user_id
        )
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        return {"success": False, "error": "Reminder not found"}

    if "title" in arguments:
        reminder.title = arguments["title"]
    if "body" in arguments:
        reminder.body = arguments["body"]
    if "trigger_at" in arguments:
        reminder.trigger_at = datetime.fromisoformat(arguments["trigger_at"])
    if "type" in arguments:
        reminder.type = arguments["type"]

    await db.flush()

    # Load pet name for card
    pet_result = await db.execute(select(Pet).where(Pet.id == reminder.pet_id))
    pet = pet_result.scalar_one_or_none()

    card = {
        "type": "reminder",
        "pet_name": pet.name if pet else "Unknown",
        "title": reminder.title,
        "trigger_at": reminder.trigger_at.isoformat() if reminder.trigger_at else None,
        "reminder_type": reminder.type,
    }

    return {
        "success": True,
        "reminder_id": str(reminder.id),
        "title": reminder.title,
        "trigger_at": reminder.trigger_at.isoformat() if reminder.trigger_at else None,
        "card": card,
    }


async def _delete_reminder(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Delete/cancel a reminder."""
    reminder_id = uuid.UUID(arguments["reminder_id"])

    result = await db.execute(
        select(Reminder).where(
            Reminder.id == reminder_id, Reminder.user_id == user_id
        )
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        return {"success": False, "error": "Reminder not found"}

    title = reminder.title
    await db.delete(reminder)
    await db.flush()

    return {
        "success": True,
        "reminder_id": str(reminder_id),
        "title": title,
        "card": {
            "type": "reminder_deleted",
            "title": title,
        },
    }


async def _upload_event_photo(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    images: list[str] | None = None,
    **_kwargs,
) -> dict:
    """Attach a photo to a calendar event."""
    event_id = uuid.UUID(arguments["event_id"])

    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id, CalendarEvent.user_id == user_id
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        return {"success": False, "error": "Event not found"}

    # Prefer image from user's attached photos, fall back to arguments
    img_b64 = (images[0] if images else None) or arguments.get("image_base64")
    if not img_b64:
        return {"success": False, "error": "No image provided. Ask the user to attach a photo."}
    image_data = base64.b64decode(img_b64)
    if len(image_data) > 5 * 1024 * 1024:
        return {"success": False, "error": "Image must be under 5MB"}

    photo_id = uuid.uuid4()
    filename = f"{photo_id}.jpg"
    filepath = PHOTO_DIR / filename
    filepath.write_bytes(image_data)

    photo_url = f"/api/v1/calendar/photos/{filename}"
    photos = list(event.photos) if event.photos else []
    photos.append(photo_url)
    event.photos = photos
    await db.flush()

    return {
        "success": True,
        "event_id": str(event_id),
        "photo_url": photo_url,
        "card": {
            "type": "record",
            "pet_name": "",
            "date": str(arguments.get("event_date", "")),
            "category": "daily",
        },
    }


async def _set_language(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Change the app display language (frontend-only action)."""
    language = arguments["language"]

    card = {
        "type": "set_language",
        "language": language,
    }

    return {
        "success": True,
        "language": language,
        "card": card,
    }


async def _set_pet_avatar(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    images: list[str] | None = None,
    **_kwargs,
) -> dict:
    """Set a pet's avatar from a base64 image."""
    pet_id = uuid.UUID(arguments["pet_id"])

    result = await db.execute(
        select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        return {"success": False, "error": "Pet not found"}

    # Prefer image from user's attached photos, fall back to arguments
    img_b64 = (images[0] if images else None) or arguments.get("image_base64")
    logger.info("set_pet_avatar_debug", extra={
        "pet_id": str(pet_id),
        "has_images": bool(images),
        "images_count": len(images) if images else 0,
        "img_b64_len": len(img_b64) if img_b64 else 0,
    })
    if not img_b64:
        return {"success": False, "error": "No image provided. Ask the user to attach a photo."}
    image_data = base64.b64decode(img_b64)
    if len(image_data) > 5 * 1024 * 1024:
        return {"success": False, "error": "Image must be under 5MB"}

    filename = f"{pet_id}.jpg"
    filepath = UPLOAD_DIR / filename
    filepath.write_bytes(image_data)
    logger.info("avatar_file_written", extra={"path": str(filepath), "size": len(image_data)})

    pet.avatar_url = f"/api/v1/pets/{pet_id}/avatar"
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


async def _trigger_emergency(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Return an emergency card for the frontend to display."""
    return {
        "success": True,
        "card": {
            "type": "emergency",
            "message": arguments["message"],
            "action": arguments["action"],
        },
    }


_TOOL_HANDLERS = {
    "create_calendar_event": _create_calendar_event,
    "query_calendar_events": _query_calendar_events,
    "update_calendar_event": _update_calendar_event,
    "create_pet": _create_pet,
    "update_pet_profile": _update_pet_profile,
    "save_pet_profile_md": _save_pet_profile_md,
    "summarize_pet_profile": _summarize_pet_profile,
    "list_pets": _list_pets,
    "create_reminder": _create_reminder,
    "search_places": _search_places,
    "draft_email": _draft_email,
    "delete_pet": _delete_pet,
    "delete_calendar_event": _delete_calendar_event,
    "list_reminders": _list_reminders,
    "update_reminder": _update_reminder,
    "delete_reminder": _delete_reminder,
    "upload_event_photo": _upload_event_photo,
    "set_language": _set_language,
    "set_pet_avatar": _set_pet_avatar,
    "trigger_emergency": _trigger_emergency,
    "request_images": None,  # Special: handled by orchestrator, not here
}

# Tools that accept extra kwargs (e.g., location, images)
_TOOLS_WITH_KWARGS = {"search_places", "upload_event_photo", "set_pet_avatar", "create_calendar_event"}


async def execute_tool(
    name: str,
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    **kwargs,
) -> dict:
    """Dispatch a tool call to the appropriate handler.

    Args:
        name: The tool function name.
        arguments: The parsed arguments dict from the LLM.
        db: An async database session.
        user_id: The authenticated user's UUID.
        **kwargs: Extra keyword arguments forwarded only to tools in _TOOLS_WITH_KWARGS.

    Returns:
        A dict with the tool execution result.

    Raises:
        ValueError: If the tool name is unknown.
    """
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")

    logger.info("tool_execute", extra={"tool": name, "arguments_keys": list(arguments.keys())})
    try:
        if name in _TOOLS_WITH_KWARGS:
            result = await handler(arguments, db, user_id, **kwargs)
        else:
            result = await handler(arguments, db, user_id)
        logger.info("tool_success", extra={"tool": name})
        return result
    except Exception as exc:
        logger.error("tool_error", extra={"tool": name, "error": str(exc)[:200]})
        raise
