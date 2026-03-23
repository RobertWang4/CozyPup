#!/usr/bin/env python3
"""
CozyPup Model Benchmark — 评估不同 LLM 在本项目 function calling 场景下的能力

用法:
    # 编辑脚本底部的 MODELS 和 API 配置
    python scripts/model_benchmark.py

    # 只测特定模型
    python scripts/model_benchmark.py --models "gpt-4o,claude-sonnet-4-20250514,deepseek-chat"

    # 跳过某些测试
    python scripts/model_benchmark.py --skip-cases "T08,T09"

    # 详细输出
    python scripts/model_benchmark.py --verbose
"""

import argparse
import asyncio
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import litellm

# ═══════════════════════════════════════════════════════════
# 配置区 — 修改这里
# ═══════════════════════════════════════════════════════════

# 中转站配置
API_BASE = "https://api.shubiaobiao.cn/v1"
API_KEY = "sk-9G7PzM3PJCjsGASj8501B233413a444aBe70525420D63728"

# 要测试的模型列表
MODELS = [
    "openai/deepseek-v3.2",
    "openai/glm-5",
    "openai/kimi-k2.5",
    "openai/qwen3.5-plus-2026-02-15",
]

# ═══════════════════════════════════════════════════════════
# Tool definitions (从项目复制, 保持一致)
# ═══════════════════════════════════════════════════════════

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": (
                "Record a pet health event to the calendar. Use this when the user mentions "
                "feeding, symptoms, medications, vaccinations, deworming, vet visits, or any "
                "daily care activity that should be logged."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {"type": "string", "description": "UUID of the pet this event is for."},
                    "event_date": {"type": "string", "description": "Date of the event in YYYY-MM-DD format."},
                    "title": {"type": "string", "description": "Short description of the event."},
                    "category": {
                        "type": "string",
                        "enum": ["diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"],
                        "description": "Category of the health event.",
                    },
                    "event_time": {"type": "string", "description": "Optional time in HH:MM format."},
                    "raw_text": {"type": "string", "description": "Optional original user text."},
                },
                "required": ["pet_id", "event_date", "title", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_calendar_events",
            "description": "Query the pet's calendar event history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {"type": "string", "description": "Optional UUID of the pet to filter by."},
                    "start_date": {"type": "string", "description": "Optional start date in YYYY-MM-DD format."},
                    "end_date": {"type": "string", "description": "Optional end date in YYYY-MM-DD format."},
                    "category": {
                        "type": "string",
                        "enum": ["diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"],
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_pet",
            "description": "Create a new pet profile for the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The pet's name."},
                    "species": {"type": "string", "enum": ["dog", "cat", "other"]},
                    "breed": {"type": "string", "description": "Breed, e.g. 'Golden Retriever'."},
                    "birthday": {"type": "string", "description": "Optional birthday in YYYY-MM-DD format."},
                    "weight": {"type": "number", "description": "Optional weight in kg."},
                    "gender": {"type": "string", "enum": ["male", "female", "unknown"]},
                    "neutered": {"type": "boolean"},
                    "coat_color": {"type": "string"},
                },
                "required": ["name", "species"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_pet_profile",
            "description": "Save any information about a pet to its profile as flexible key-value pairs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {"type": "string", "description": "UUID of the pet."},
                    "info": {"type": "object", "description": "Key-value pairs of pet info to save."},
                },
                "required": ["pet_id", "info"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pets",
            "description": "List all of the user's registered pets with their profiles.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Create a reminder that will send a push notification at the specified time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {"type": "string", "description": "UUID of the pet."},
                    "type": {
                        "type": "string",
                        "enum": ["medication", "vaccine", "checkup", "feeding", "grooming", "other"],
                    },
                    "title": {"type": "string", "description": "Short reminder title."},
                    "body": {"type": "string", "description": "Optional detailed description."},
                    "trigger_at": {"type": "string", "description": "ISO 8601 format (YYYY-MM-DDTHH:MM:SS)."},
                },
                "required": ["pet_id", "type", "title", "trigger_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_places",
            "description": "Search for nearby pet-related places like veterinary clinics, pet stores, dog parks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for Google Places."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_email",
            "description": "Present a draft email as a card for the user to review and send.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Email subject line."},
                    "body": {"type": "string", "description": "Full email body text."},
                },
                "required": ["subject", "body"],
            },
        },
    },
]

# ═══════════════════════════════════════════════════════════
# System prompt (和项目保持一致)
# ═══════════════════════════════════════════════════════════

TODAY = date.today().isoformat()
FAKE_PET_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
FAKE_PET_ID_2 = "b2c3d4e5-f6a7-8901-bcde-f12345678901"

SYSTEM_PROMPT = f"""You are CozyPup, a friendly and knowledgeable pet health assistant.
You help pet owners with health questions, care tips, and general pet wellness guidance.

Today's date: {TODAY}

Important rules:
- Always be warm, supportive, and encouraging.
- For health-related questions, provide helpful guidance but always recommend consulting a veterinarian for serious concerns.
- End health-related responses with: "This is general guidance only and not a substitute for professional veterinary advice."
- You MUST respond in the same language the user uses. If the user writes in Chinese, respond entirely in Chinese. If in English, respond in English. Match the user's language exactly.
- Keep responses concise and practical.

## CRITICAL: You MUST use tools

You have tools available. When the user's message matches a tool's purpose, you MUST call that tool. Do NOT just describe what you would do — actually call the tool. Never say "I recorded..." or "I've set..." without making a real tool call first.

### Tools

- **create_pet** — Create a new pet profile. MUST call when the user mentions a new pet.
- **update_pet_profile** — Save ANY info about a pet as flexible key-value pairs. Call proactively whenever the user mentions pet details.
- **list_pets** — List all registered pets with IDs.
- **create_calendar_event** — Record events to the calendar. Call when the user mentions something that happened to their pet.
- **query_calendar_events** — Look up past health events or history.
- **create_reminder** — Set a push notification reminder.
- **search_places** — Find nearby vets, pet stores, dog parks.
- **draft_email** — Draft a professional email. YOU compose the subject and body, then call this tool.

## Multi-pet handling

The user's pets are listed below. When referring to a specific pet:
- If they specify which pet (by name), use that pet's ID.
- If there is only one pet, use that pet's ID.
- If ambiguous, ask the user to clarify.

### User's Pets:
1. 布丁 (Pudding) — 金毛 Golden Retriever, dog — ID: {FAKE_PET_ID}
2. 咪咪 (Mimi) — 英短 British Shorthair, cat — ID: {FAKE_PET_ID_2}"""

# ═══════════════════════════════════════════════════════════
# Validation helpers
# ═══════════════════════════════════════════════════════════

CATEGORIES = {"diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"}
SPECIES = {"dog", "cat", "other"}
REMINDER_TYPES = {"medication", "vaccine", "checkup", "feeding", "grooming", "other"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def is_valid_uuid(s: str) -> bool:
    try:
        uuid.UUID(str(s))
        return True
    except (ValueError, AttributeError):
        return False


def is_valid_date(s: str) -> bool:
    if not DATE_RE.match(str(s)):
        return False
    try:
        date.fromisoformat(str(s))
        return True
    except ValueError:
        return False


def is_valid_time(s: str) -> bool:
    return bool(TIME_RE.match(str(s)))


def is_valid_datetime(s: str) -> bool:
    try:
        datetime.fromisoformat(str(s))
        return True
    except (ValueError, TypeError):
        return False


# ═══════════════════════════════════════════════════════════
# Test case definitions
# ═══════════════════════════════════════════════════════════

@dataclass
class TestResult:
    """Single test case result for one model."""
    passed: bool = False
    scores: dict[str, float] = field(default_factory=dict)  # dimension -> 0.0~1.0
    tool_calls: list[dict] = field(default_factory=list)
    text_response: str = ""
    error: str = ""
    latency_ms: int = 0


@dataclass
class TestCase:
    """One test scenario."""
    id: str
    name: str
    description: str
    user_message: str
    # Evaluation criteria
    expected_tools: list[str]  # tool names that SHOULD be called
    forbidden_tools: list[str] = field(default_factory=list)  # tools that MUST NOT be called
    check_fn: Any = None  # callable(tool_calls, text) -> dict[str, float] for detailed scoring
    dimensions: list[str] = field(default_factory=list)  # which scoring dimensions apply


# --- Individual check functions ---

def check_t01(tool_calls: list[dict], text: str) -> dict[str, float]:
    """T01: 简单记录 — 布丁今天吃了狗粮"""
    scores = {}
    tc = _find_tool(tool_calls, "create_calendar_event")
    if not tc:
        return {"tool_call": 0, "schema": 0, "category": 0, "pet_id": 0}
    args = tc.get("args", {})
    scores["tool_call"] = 1.0
    # Schema: required fields present + valid formats
    schema_checks = [
        args.get("pet_id") and is_valid_uuid(args["pet_id"]),
        args.get("event_date") and is_valid_date(args["event_date"]),
        bool(args.get("title")),
        args.get("category") in CATEGORIES,
    ]
    scores["schema"] = sum(schema_checks) / len(schema_checks)
    # Category should be "diet"
    scores["category"] = 1.0 if args.get("category") == "diet" else 0.0
    # Should use 布丁's ID
    scores["pet_id"] = 1.0 if args.get("pet_id") == FAKE_PET_ID else 0.0
    return scores


def check_t02(tool_calls: list[dict], text: str) -> dict[str, float]:
    """T02: 复杂记录 — 布丁早上8点打了狂犬疫苗"""
    scores = {}
    tc = _find_tool(tool_calls, "create_calendar_event")
    if not tc:
        return {"tool_call": 0, "schema": 0, "category": 0, "time_extraction": 0, "pet_id": 0}
    args = tc.get("args", {})
    scores["tool_call"] = 1.0
    scores["schema"] = 1.0 if all([
        is_valid_uuid(args.get("pet_id", "")),
        is_valid_date(args.get("event_date", "")),
        args.get("title"),
        args.get("category") in CATEGORIES,
    ]) else 0.5
    scores["category"] = 1.0 if args.get("category") == "vaccine" else 0.0
    # Time extraction: should be 08:00
    et = args.get("event_time", "")
    scores["time_extraction"] = 1.0 if et == "08:00" else (0.5 if is_valid_time(et) else 0.0)
    scores["pet_id"] = 1.0 if args.get("pet_id") == FAKE_PET_ID else 0.0
    return scores


def check_t03(tool_calls: list[dict], text: str) -> dict[str, float]:
    """T03: 查询历史 — 布丁上个月的喂食记录"""
    scores = {}
    tc = _find_tool(tool_calls, "query_calendar_events")
    if not tc:
        return {"tool_call": 0, "schema": 0, "date_range": 0, "category_filter": 0}
    args = tc.get("args", {})
    scores["tool_call"] = 1.0
    # Should have start_date and end_date
    has_dates = bool(args.get("start_date")) and bool(args.get("end_date"))
    scores["date_range"] = 1.0 if has_dates else (0.5 if args.get("start_date") or args.get("end_date") else 0.0)
    # Should filter by category=diet
    scores["category_filter"] = 1.0 if args.get("category") == "diet" else 0.0
    # Date format validity
    schema_ok = True
    for f in ["start_date", "end_date"]:
        if args.get(f) and not is_valid_date(args[f]):
            schema_ok = False
    scores["schema"] = 1.0 if schema_ok else 0.0
    return scores


def check_t04(tool_calls: list[dict], text: str) -> dict[str, float]:
    """T04: 创建宠物 — 新养了一只金毛叫大黄"""
    scores = {}
    tc = _find_tool(tool_calls, "create_pet")
    if not tc:
        return {"tool_call": 0, "schema": 0, "info_extraction": 0}
    args = tc.get("args", {})
    scores["tool_call"] = 1.0
    scores["schema"] = 1.0 if args.get("name") and args.get("species") in SPECIES else 0.0
    # Info extraction: name=大黄, species=dog, breed=金毛/Golden Retriever, age→birthday
    info_checks = [
        "大黄" in args.get("name", ""),
        args.get("species") == "dog",
        bool(args.get("breed")),  # should extract 金毛
    ]
    scores["info_extraction"] = sum(info_checks) / len(info_checks)
    return scores


def check_t05(tool_calls: list[dict], text: str) -> dict[str, float]:
    """T05: 设置提醒 — 提醒我明天下午3点带布丁去打疫苗"""
    scores = {}
    tc = _find_tool(tool_calls, "create_reminder")
    if not tc:
        return {"tool_call": 0, "schema": 0, "time_accuracy": 0, "type_accuracy": 0}
    args = tc.get("args", {})
    scores["tool_call"] = 1.0
    # Schema validation
    schema_ok = all([
        is_valid_uuid(args.get("pet_id", "")),
        args.get("type") in REMINDER_TYPES,
        bool(args.get("title")),
        is_valid_datetime(args.get("trigger_at", "")),
    ])
    scores["schema"] = 1.0 if schema_ok else 0.0
    # Time accuracy: should be tomorrow 15:00
    trigger = args.get("trigger_at", "")
    if trigger:
        try:
            dt = datetime.fromisoformat(trigger)
            tomorrow = date.today().toordinal() + 1
            is_tomorrow = dt.date().toordinal() == tomorrow
            is_3pm = dt.hour == 15 and dt.minute == 0
            scores["time_accuracy"] = (0.5 if is_tomorrow else 0) + (0.5 if is_3pm else 0)
        except (ValueError, TypeError):
            scores["time_accuracy"] = 0.0
    else:
        scores["time_accuracy"] = 0.0
    scores["type_accuracy"] = 1.0 if args.get("type") == "vaccine" else 0.0
    return scores


def check_t06(tool_calls: list[dict], text: str) -> dict[str, float]:
    """T06: 搜索地点 — 附近有没有宠物医院"""
    scores = {}
    tc = _find_tool(tool_calls, "search_places")
    if not tc:
        return {"tool_call": 0, "query_quality": 0}
    args = tc.get("args", {})
    scores["tool_call"] = 1.0
    q = args.get("query", "").lower()
    # Query should be about veterinary/pet hospital
    vet_keywords = ["vet", "veterinary", "animal hospital", "pet hospital", "宠物医院", "兽医"]
    scores["query_quality"] = 1.0 if any(k in q for k in vet_keywords) else 0.5
    return scores


def check_t07(tool_calls: list[dict], text: str) -> dict[str, float]:
    """T07: 纯聊天 — 金毛适合吃什么狗粮"""
    scores = {}
    # Should NOT call any tools
    scores["no_false_tool_call"] = 1.0 if len(tool_calls) == 0 else 0.0
    # Should have substantive text response
    scores["response_quality"] = 1.0 if len(text) > 50 else (0.5 if len(text) > 20 else 0.0)
    # Should contain health disclaimer (in Chinese or English)
    disclaimer_keywords = ["兽医", "veterinary", "veterinarian", "专业", "professional", "建议", "advice"]
    scores["disclaimer"] = 1.0 if any(k in text.lower() for k in disclaimer_keywords) else 0.0
    return scores


def check_t08(tool_calls: list[dict], text: str) -> dict[str, float]:
    """T08: 多宠物歧义 — 他今天吐了 (ambiguous — who is '他'?)"""
    scores = {}
    # Model should either: (a) ask for clarification, or (b) call tool but it's risky
    has_tool = len(tool_calls) > 0
    # Check if text asks for clarification
    clarify_keywords = ["哪", "which", "谁", "clarif", "指的是", "是布丁还是", "是哪只"]
    asks_clarification = any(k in text.lower() for k in clarify_keywords)
    if asks_clarification and not has_tool:
        scores["ambiguity_handling"] = 1.0  # Best: asks for clarification
    elif has_tool:
        # Acceptable if it picked one but should ideally ask
        scores["ambiguity_handling"] = 0.3
    else:
        scores["ambiguity_handling"] = 0.0
    return scores


def check_t09(tool_calls: list[dict], text: str) -> dict[str, float]:
    """T09: 紧急情况 — 我的猫突然抽搐不停"""
    scores = {}
    # Should respond urgently and mention emergency/vet
    urgent_keywords = ["急", "紧急", "urgent", "emergency", "immediately", "立刻", "马上", "赶紧", "尽快"]
    vet_keywords = ["医院", "兽医", "vet", "hospital", "急诊"]
    scores["urgency"] = 1.0 if any(k in text.lower() for k in urgent_keywords) else 0.0
    scores["vet_referral"] = 1.0 if any(k in text.lower() for k in vet_keywords) else 0.0
    # Bonus: if it also calls search_places for emergency vet
    if _find_tool(tool_calls, "search_places"):
        scores["proactive_search"] = 1.0
    else:
        scores["proactive_search"] = 0.0  # Not required but nice to have
    return scores


def check_t10(tool_calls: list[dict], text: str) -> dict[str, float]:
    """T10: 语言匹配 — English input should get English response"""
    scores = {}
    # Check if response is in English (no Chinese characters)
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    scores["language_match"] = 1.0 if len(chinese_chars) == 0 else (0.5 if len(chinese_chars) < 5 else 0.0)
    # Should still call create_calendar_event
    tc = _find_tool(tool_calls, "create_calendar_event")
    scores["tool_call"] = 1.0 if tc else 0.0
    if tc:
        args = tc.get("args", {})
        scores["schema"] = 1.0 if all([
            is_valid_uuid(args.get("pet_id", "")),
            is_valid_date(args.get("event_date", "")),
            args.get("title"),
            args.get("category") in CATEGORIES,
        ]) else 0.0
    return scores


def check_t11(tool_calls: list[dict], text: str) -> dict[str, float]:
    """T11: 多工具调用 — 记录+提醒"""
    scores = {}
    has_event = _find_tool(tool_calls, "create_calendar_event") is not None
    has_reminder = _find_tool(tool_calls, "create_reminder") is not None
    scores["multi_tool"] = 1.0 if (has_event and has_reminder) else (0.5 if has_event or has_reminder else 0.0)
    # Validate each tool's schema
    if has_event:
        tc = _find_tool(tool_calls, "create_calendar_event")
        args = tc.get("args", {})
        scores["event_schema"] = 1.0 if all([
            is_valid_uuid(args.get("pet_id", "")),
            is_valid_date(args.get("event_date", "")),
            args.get("category") in CATEGORIES,
        ]) else 0.0
    if has_reminder:
        tc = _find_tool(tool_calls, "create_reminder")
        args = tc.get("args", {})
        scores["reminder_schema"] = 1.0 if all([
            is_valid_uuid(args.get("pet_id", "")),
            args.get("type") in REMINDER_TYPES,
            is_valid_datetime(args.get("trigger_at", "")),
        ]) else 0.0
    return scores


def check_t12(tool_calls: list[dict], text: str) -> dict[str, float]:
    """T12: 隐式信息提取 — 对话中提到宠物信息应主动保存"""
    scores = {}
    tc = _find_tool(tool_calls, "update_pet_profile")
    if not tc:
        return {"proactive_save": 0, "info_quality": 0}
    args = tc.get("args", {})
    scores["proactive_save"] = 1.0
    info = args.get("info", {})
    # Should extract: allergy info
    has_allergy = any("allerg" in str(k).lower() or "过敏" in str(k) for k in list(info.keys()) + list(str(v) for v in info.values()))
    scores["info_quality"] = 1.0 if has_allergy else 0.5
    return scores


def check_t13(tool_calls: list[dict], text: str) -> dict[str, float]:
    """T13: 帮我给兽医写封邮件 — draft_email"""
    scores = {}
    tc = _find_tool(tool_calls, "draft_email")
    if not tc:
        return {"tool_call": 0, "email_quality": 0}
    args = tc.get("args", {})
    scores["tool_call"] = 1.0
    subject = args.get("subject", "")
    body = args.get("body", "")
    # Email should be professional and mention the pet's condition
    scores["email_quality"] = 1.0 if (len(subject) > 5 and len(body) > 50) else 0.5
    return scores


# --- Test cases ---

TEST_CASES: list[TestCase] = [
    TestCase(
        id="T01", name="简单记录",
        description="基本 function calling: 理解喂食→创建日历事件",
        user_message="布丁今天吃了两顿狗粮",
        expected_tools=["create_calendar_event"],
        check_fn=check_t01,
        dimensions=["tool_call", "schema", "category", "pet_id"],
    ),
    TestCase(
        id="T02", name="复杂记录(时间+类别)",
        description="提取时间信息, 正确分类疫苗",
        user_message="布丁今天早上8点打了狂犬疫苗",
        expected_tools=["create_calendar_event"],
        check_fn=check_t02,
        dimensions=["tool_call", "schema", "category", "time_extraction", "pet_id"],
    ),
    TestCase(
        id="T03", name="查询历史事件",
        description="理解'上个月'→计算日期范围, 过滤类别",
        user_message="帮我查一下布丁上个月的喂食记录",
        expected_tools=["query_calendar_events"],
        check_fn=check_t03,
        dimensions=["tool_call", "schema", "date_range", "category_filter"],
    ),
    TestCase(
        id="T04", name="创建宠物",
        description="从自然语言提取宠物信息, 创建 profile",
        user_message="我新养了一只金毛，叫大黄，3岁了，公的，大概30公斤",
        expected_tools=["create_pet"],
        check_fn=check_t04,
        dimensions=["tool_call", "schema", "info_extraction"],
    ),
    TestCase(
        id="T05", name="设置提醒",
        description="理解'明天下午3点'→计算 ISO 8601 datetime",
        user_message="提醒我明天下午3点带布丁去打疫苗",
        expected_tools=["create_reminder"],
        check_fn=check_t05,
        dimensions=["tool_call", "schema", "time_accuracy", "type_accuracy"],
    ),
    TestCase(
        id="T06", name="搜索地点",
        description="理解地点搜索意图, 生成合适 query",
        user_message="附近有没有宠物医院？",
        expected_tools=["search_places"],
        check_fn=check_t06,
        dimensions=["tool_call", "query_quality"],
    ),
    TestCase(
        id="T07", name="纯聊天(不该调用工具)",
        description="不需要工具的问题, 不应误调用, 且带健康免责声明",
        user_message="金毛犬一般适合吃什么品牌的狗粮？",
        expected_tools=[],
        forbidden_tools=["create_calendar_event", "create_pet"],
        check_fn=check_t07,
        dimensions=["no_false_tool_call", "response_quality", "disclaimer"],
    ),
    TestCase(
        id="T08", name="多宠物歧义",
        description="用户有两只宠物, '他'指代不明, 应询问澄清",
        user_message="他今天吐了两次",
        expected_tools=[],  # Best behavior is to ask, not blindly call
        check_fn=check_t08,
        dimensions=["ambiguity_handling"],
    ),
    TestCase(
        id="T09", name="紧急情况识别",
        description="识别紧急症状, 建议立即就医",
        user_message="我的猫咪咪突然抽搐不停，眼睛翻白",
        expected_tools=[],
        check_fn=check_t09,
        dimensions=["urgency", "vet_referral", "proactive_search"],
    ),
    TestCase(
        id="T10", name="英文语言匹配",
        description="用户英文提问→英文回复, 同时正确调用工具",
        user_message="Pudding vomited this morning around 9am, please log it.",
        expected_tools=["create_calendar_event"],
        check_fn=check_t10,
        dimensions=["language_match", "tool_call", "schema"],
    ),
    TestCase(
        id="T11", name="多工具调用",
        description="一句话触发两个工具: 记录事件 + 设置提醒",
        user_message="布丁今天吃了驱虫药，帮我记一下，另外提醒我下个月22号再吃一次",
        expected_tools=["create_calendar_event", "create_reminder"],
        check_fn=check_t11,
        dimensions=["multi_tool", "event_schema", "reminder_schema"],
    ),
    TestCase(
        id="T12", name="隐式信息提取(主动保存)",
        description="对话中提到宠物信息, 应主动调用 update_pet_profile 保存",
        user_message="布丁最近换了狗粮之后一直拉肚子，可能对鸡肉过敏",
        expected_tools=["update_pet_profile"],  # should proactively save allergy info
        check_fn=check_t12,
        dimensions=["proactive_save", "info_quality"],
    ),
    TestCase(
        id="T13", name="写邮件",
        description="帮用户写邮件给兽医, 调用 draft_email",
        user_message="帮我给兽医写封邮件，说布丁最近拉肚子一周了，想预约检查",
        expected_tools=["draft_email"],
        check_fn=check_t13,
        dimensions=["tool_call", "email_quality"],
    ),
]


# ═══════════════════════════════════════════════════════════
# LLM call & evaluation engine
# ═══════════════════════════════════════════════════════════

def _find_tool(tool_calls: list[dict], name: str) -> dict | None:
    for tc in tool_calls:
        if tc.get("name") == name:
            return tc
    return None


async def call_model(model: str, user_message: str) -> tuple[str, list[dict], int]:
    """Call a model and return (text_response, tool_calls, latency_ms).

    tool_calls format: [{"name": str, "args": dict}, ...]
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    start = time.monotonic()
    try:
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            temperature=0.3,
            api_base=API_BASE,
            api_key=API_KEY,
        )
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return f"[ERROR: {e}]", [], elapsed

    elapsed = int((time.monotonic() - start) * 1000)

    choice = response.choices[0]
    text = choice.message.content or ""
    raw_tool_calls = choice.message.tool_calls or []

    tool_calls = []
    for tc in raw_tool_calls:
        try:
            args = json.loads(tc.function.arguments)
        except (json.JSONDecodeError, AttributeError):
            args = {}
        tool_calls.append({"name": tc.function.name, "args": args, "id": getattr(tc, "id", "")})

    return text, tool_calls, elapsed


async def run_test(model: str, case: TestCase, verbose: bool = False) -> TestResult:
    """Run a single test case against a model."""
    result = TestResult()
    try:
        text, tool_calls, latency = await call_model(model, case.user_message)
        result.text_response = text
        result.tool_calls = tool_calls
        result.latency_ms = latency

        if text.startswith("[ERROR:"):
            result.error = text
            return result

        # Run the check function
        if case.check_fn:
            result.scores = case.check_fn(tool_calls, text)

        # Overall pass: all scores >= 0.5
        result.passed = all(v >= 0.5 for v in result.scores.values()) if result.scores else False

        if verbose:
            _print_verbose(model, case, result)

    except Exception as e:
        result.error = str(e)

    return result


def _print_verbose(model: str, case: TestCase, result: TestResult):
    print(f"\n  {'='*60}")
    print(f"  [{case.id}] {case.name} — {model}")
    print(f"  User: {case.user_message}")
    print(f"  Latency: {result.latency_ms}ms")
    if result.tool_calls:
        for tc in result.tool_calls:
            print(f"  Tool: {tc['name']}({json.dumps(tc['args'], ensure_ascii=False)[:200]})")
    if result.text_response:
        preview = result.text_response[:150].replace('\n', ' ')
        print(f"  Text: {preview}{'...' if len(result.text_response) > 150 else ''}")
    for dim, score in result.scores.items():
        icon = "✓" if score >= 0.5 else "✗"
        print(f"  {icon} {dim}: {score:.1f}")
    if result.error:
        print(f"  ERROR: {result.error}")


# ═══════════════════════════════════════════════════════════
# Report generation
# ═══════════════════════════════════════════════════════════

def print_report(all_results: dict[str, dict[str, TestResult]], models: list[str]):
    """Print the final comparison table."""
    print("\n")
    print("=" * 80)
    print("  CozyPup Model Benchmark Report")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)

    # --- Per-test comparison ---
    print("\n## 各测试用例得分\n")
    header = f"{'Test':<6} {'Name':<20} " + " ".join(f"{m[:12]:>12}" for m in models)
    print(header)
    print("-" * len(header))

    for case in TEST_CASES:
        scores_str = []
        for model in models:
            r = all_results.get(model, {}).get(case.id)
            if r and r.scores:
                avg = sum(r.scores.values()) / len(r.scores)
                icon = "✓" if r.passed else "✗"
                scores_str.append(f"{icon} {avg:.0%}".rjust(12))
            elif r and r.error:
                scores_str.append("ERR".rjust(12))
            else:
                scores_str.append("-".rjust(12))
        print(f"{case.id:<6} {case.name:<20} " + " ".join(scores_str))

    # --- Dimension aggregation ---
    print("\n\n## 维度评分汇总\n")
    all_dims = set()
    for model in models:
        for case_id, r in all_results.get(model, {}).items():
            all_dims.update(r.scores.keys())

    dim_groups = {
        "Tool Calling": ["tool_call", "multi_tool", "no_false_tool_call", "proactive_save", "proactive_search"],
        "Schema 合规": ["schema", "event_schema", "reminder_schema"],
        "语义理解": ["category", "category_filter", "info_extraction", "info_quality", "query_quality",
                      "email_quality", "time_extraction", "time_accuracy", "type_accuracy", "date_range"],
        "对话质量": ["response_quality", "disclaimer", "language_match", "urgency", "vet_referral",
                     "ambiguity_handling"],
    }

    header2 = f"{'Dimension':<20} " + " ".join(f"{m[:12]:>12}" for m in models)
    print(header2)
    print("-" * len(header2))

    for group_name, dims in dim_groups.items():
        group_scores = {}
        for model in models:
            scores_in_group = []
            for case_id, r in all_results.get(model, {}).items():
                for d in dims:
                    if d in r.scores:
                        scores_in_group.append(r.scores[d])
            group_scores[model] = sum(scores_in_group) / len(scores_in_group) if scores_in_group else 0
        scores_line = " ".join(f"{group_scores[m]:.0%}".rjust(12) for m in models)
        print(f"{group_name:<20} {scores_line}")

    # --- Latency ---
    print("\n\n## 平均延迟\n")
    header3 = f"{'Metric':<20} " + " ".join(f"{m[:12]:>12}" for m in models)
    print(header3)
    print("-" * len(header3))
    latencies = {}
    for model in models:
        lats = [r.latency_ms for r in all_results.get(model, {}).values() if r.latency_ms > 0]
        latencies[model] = sum(lats) / len(lats) if lats else 0
    lat_line = " ".join(f"{latencies[m]:.0f}ms".rjust(12) for m in models)
    print(f"{'Avg latency':<20} {lat_line}")

    # --- Final score ---
    print("\n\n## 综合评分 (0-100)\n")
    header4 = f"{'Model':<25} {'Score':>8} {'Grade':>8}"
    print(header4)
    print("-" * len(header4))

    final_scores = {}
    for model in models:
        all_scores = []
        for case_id, r in all_results.get(model, {}).items():
            if r.scores:
                all_scores.extend(r.scores.values())
        final = (sum(all_scores) / len(all_scores) * 100) if all_scores else 0
        final_scores[model] = final

    # Sort by score
    for model in sorted(models, key=lambda m: final_scores[m], reverse=True):
        score = final_scores[model]
        if score >= 90:
            grade = "A"
        elif score >= 80:
            grade = "B+"
        elif score >= 70:
            grade = "B"
        elif score >= 60:
            grade = "C"
        elif score >= 40:
            grade = "D"
        else:
            grade = "F"
        print(f"{model:<25} {score:>7.1f} {grade:>8}")

    print("\n" + "=" * 80)
    print("  评分标准:")
    print("  - Tool Calling: 是否调用了正确的工具, 没有误调用")
    print("  - Schema 合规: 参数格式(UUID/日期/枚举)是否正确")
    print("  - 语义理解: 从自然语言提取信息的准确度(时间/类别/宠物信息)")
    print("  - 对话质量: 回复语言/语气/免责声明/紧急情况处理")
    print("=" * 80)


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description="CozyPup Model Benchmark")
    parser.add_argument("--models", type=str, help="Comma-separated model list (override default)")
    parser.add_argument("--skip-cases", type=str, help="Comma-separated test IDs to skip")
    parser.add_argument("--only-cases", type=str, help="Comma-separated test IDs to run")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output per test")
    parser.add_argument("--api-base", type=str, help="Override API base URL")
    parser.add_argument("--api-key", type=str, help="Override API key")
    parser.add_argument("--json", type=str, help="Save raw results to JSON file")
    args = parser.parse_args()

    global API_BASE, API_KEY
    if args.api_base:
        API_BASE = args.api_base
    if args.api_key:
        API_KEY = args.api_key

    models = args.models.split(",") if args.models else MODELS
    skip = set(args.skip_cases.split(",")) if args.skip_cases else set()
    only = set(args.only_cases.split(",")) if args.only_cases else None

    cases = [c for c in TEST_CASES if c.id not in skip and (only is None or c.id in only)]

    print(f"CozyPup Model Benchmark")
    print(f"Models: {', '.join(models)}")
    print(f"Tests:  {len(cases)} cases")
    print(f"API:    {API_BASE}")
    print()

    all_results: dict[str, dict[str, TestResult]] = {}

    for model in models:
        print(f"\n--- Testing: {model} ---")
        all_results[model] = {}

        for case in cases:
            sys.stdout.write(f"  {case.id} {case.name}... ")
            sys.stdout.flush()
            result = await run_test(model, case, verbose=args.verbose)
            all_results[model][case.id] = result

            if result.error:
                print(f"ERROR: {result.error[:60]}")
            elif result.passed:
                avg = sum(result.scores.values()) / len(result.scores)
                print(f"PASS ({avg:.0%}, {result.latency_ms}ms)")
            else:
                avg = sum(result.scores.values()) / len(result.scores) if result.scores else 0
                print(f"FAIL ({avg:.0%}, {result.latency_ms}ms)")

    print_report(all_results, models)

    # Optionally save raw results
    if args.json:
        raw = {}
        for model, cases_map in all_results.items():
            raw[model] = {}
            for case_id, r in cases_map.items():
                raw[model][case_id] = {
                    "passed": r.passed,
                    "scores": r.scores,
                    "tool_calls": [{"name": tc["name"], "args": tc["args"]} for tc in r.tool_calls],
                    "text_preview": r.text_response[:300],
                    "latency_ms": r.latency_ms,
                    "error": r.error,
                }
        with open(args.json, "w") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
        print(f"\nRaw results saved to {args.json}")


if __name__ == "__main__":
    asyncio.run(main())
