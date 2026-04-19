"""Shared constants + confirm-gate policy for the agent pipeline.

Defines which tools always need a user confirm card, which can skip the
Round 2 LLM call after execution, and the regex rules that bypass
confirmation when the user's message already contains an explicit
action verb.

Consumed by `orchestrator.dispatch_tool` and the chat router — all
confirmation decisions live here so the LLM never decides whether to
ask the user.
"""

import asyncio
import re

# Always-confirm tools: destructive or irreversible. No verb bypass.
CONFIRM_TOOLS = {
    "delete_pet",
    "delete_calendar_event",
    "delete_reminder",
    "delete_all_reminders",
    "remove_event_photo",
}

# Mutating tools that default to confirm, but auto-skip when user message
# contains an explicit action verb (mechanical regex match, no LLM involved).
MUTATING_TOOLS_WITH_VERB_BYPASS = {
    "create_calendar_event",
    "update_calendar_event",
    "update_pet_profile",
    "create_pet",
    "create_reminder",
    "update_reminder",
    "create_daily_task",
    "manage_daily_task",
    "set_pet_avatar",
    "draft_email",
    "set_language",
    "save_pet_profile_md",
    "summarize_pet_profile",
    "add_event_location",
    "upload_event_photo",
}

# Global explicit-action verbs: ANY mutating tool bypasses confirm when these
# match. Covers cases where the user commanded an action, regardless of which
# specific tool the LLM chose (e.g. "提醒我..." → user may get create_reminder
# OR create_calendar_event+reminder_at; both should bypass).
_GLOBAL_EXPLICIT_VERBS = re.compile(
    r"记一?下|记下|写下来|帮我?记|记录|保存|存一下|添加|加一条|新建|登记|备注|记作|标注|标记|入账|入档|"
    r"改成|改为|修改|更正|纠正|调整|换成|改到|改掉|写错了|记错了|搞错了|"
    r"提醒我|帮.*提醒|设.*提醒|叫我|闹钟|"
    r"record|save|add|log|note|create|update|set|change to|modify|correct|fix|remind me"
)

# Per-tool explicit verb regex. Match = user clearly asked for the action → auto-execute.
# Tool-specific verbs (additional to _GLOBAL_EXPLICIT_VERBS).
# No match = treat like delete_*, pop confirm card.
_VERB_BYPASS_RULES: dict[str, re.Pattern] = {
    "create_calendar_event": re.compile(
        r"记一?下|记下|写下来|帮我?记|记录|保存|存一下|添加|加一条|新建|登记|备注|标记|入账|入档|"
        r"record|save|add|log|note|create"
    ),
    "update_calendar_event": re.compile(
        r"改成|改为|修改|更正|纠正|调整|换成|改到|改掉|写错了|记错了|搞错了|"
        r"change to|modify|update|correct|fix"
    ),
    "update_pet_profile": re.compile(
        r"更新|记下|改成|改为|修改|设置.*为|备注|记作|标注|档案.*(?:加|记|存)|"
        r"update|set|change to|modify"
    ),
    "create_pet": re.compile(
        r"加一只|加只|新增.*宠物|养了|新养|领了|领养|带回|买了只|新来的|创建.*档案|"
        r"add (?:a )?pet|got a new|adopted|bought a"
    ),
    "create_reminder": re.compile(
        r"提醒我|帮.*提醒|设.*提醒|叫我|到时候.*我|闹钟|记得.*(?:明天|后天|下周|下个月|下次|打|吃|喂|带)|"
        r"remind me|set.*reminder|alert me"
    ),
    "update_reminder": re.compile(
        r"改提醒|改闹钟|提醒.*(?:改|调|挪|移)|把提醒|调提醒|挪提醒|"
        r"change.*reminder|update.*reminder|move.*reminder"
    ),
    "create_daily_task": re.compile(
        r"加.*日常|加.*每日|加个任务|加.*代办|每天.*提醒|日常.*加|"
        r"add.*daily|daily task|every day"
    ),
    "manage_daily_task": re.compile(
        r"改.*日常|改.*每日|日常.*改|每日.*改|开启|激活|"
        r"update.*daily|modify.*daily|enable"
    ),
    "set_pet_avatar": re.compile(
        r"换.*头像|设.*头像|(?:这张|这个).*(?:做|当|设为|用).*头像|头像.*(?:改|换|设|就用|用这)|"
        r"用.*(?:这张|这个).*头像|"
        r"set.*avatar|change.*avatar|use.*as.*avatar|profile.*(?:pic|photo|image)"
    ),
    "draft_email": re.compile(
        r"写.*邮件|草拟|起草|发.*邮件|帮我.*邮件|邮件.*给|"
        r"draft.*email|write.*email|compose.*email|email.*to"
    ),
    "set_language": re.compile(
        r"切换.*(?:中文|英文|english|chinese)|(?:改|换).*(?:中文|英文|english|chinese)|"
        r"(?:说|用|讲).*(?:中文|英文|english|chinese)|"
        r"switch.*(?:english|chinese)|speak.*(?:english|chinese)|change.*language"
    ),
    "save_pet_profile_md": re.compile(
        r"保存.*档案|整理.*档案|更新.*档案|总结.*档案|档案.*(?:保存|整理|更新)|"
        r"save.*profile|organize.*profile|update.*profile"
    ),
    "summarize_pet_profile": re.compile(
        r"总结|整理|汇总|生成.*报告|summarize|summary|generate.*report"
    ),
    "add_event_location": re.compile(
        # Generic recording verbs count (usually chained with event creation),
        # plus explicit location-attach phrasings.
        r"记一?下|记下|帮我?记|记录|保存|添加|加一条|新建|登记|"
        r"加.*地点|加.*位置|关联.*地点|关联.*位置|记.*地点|在.*(?:咖啡|公园|医院|店|街|路)|"
        r"record|save|add|log|attach.*location|tag.*location|at "
    ),
    "upload_event_photo": re.compile(
        # Usually chained with event creation when user sends photo.
        r"记一?下|记下|帮我?记|记录|保存|添加|加一条|新建|登记|"
        r"加.*照片|加.*图片|上传.*照片|附上.*照片|"
        r"record|save|add|log|upload.*photo|attach.*photo"
    ),
}

# Tools whose confirmation depends on the action argument.
# Maps tool name → set of actions that trigger confirmation.
CONDITIONAL_CONFIRM_ACTIONS = {
    "manage_daily_task": {"delete", "delete_all", "deactivate"},
}


def _verb_matches(fn_name: str, user_text: str) -> bool:
    if not user_text:
        return False
    text = user_text.lower()
    # Global action verbs bypass for any mutating tool.
    if _GLOBAL_EXPLICIT_VERBS.search(text):
        return True
    rule = _VERB_BYPASS_RULES.get(fn_name)
    if rule is None:
        return False
    return bool(rule.search(text))


def needs_confirm(fn_name: str, fn_args: dict, user_text: str = "") -> bool:
    """Return True if this tool call requires a confirm card.

    Rules (in order):
    1. CONFIRM_TOOLS → always confirm (no bypass).
    2. CONDITIONAL_CONFIRM_ACTIONS hit → always confirm.
    3. MUTATING_TOOLS_WITH_VERB_BYPASS → confirm UNLESS user message has
       explicit verb (mechanical regex). No LLM involvement.
    """
    if fn_name in CONFIRM_TOOLS:
        return True
    actions = CONDITIONAL_CONFIRM_ACTIONS.get(fn_name)
    if actions and fn_args.get("action") in actions:
        return True
    if fn_name in MUTATING_TOOLS_WITH_VERB_BYPASS:
        return not _verb_matches(fn_name, user_text)
    return False

# Tools that the LLM frequently forgets to call — nudge and post-processor
# will only force these. All other pre-processor suggestions are advisory only.
NUDGE_TOOLS = {"search_places", "trigger_emergency", "set_language"}

# Tools whose results are simple enough to skip the Round 2 LLM call.
# After successful execution, we use the LLM's streaming text from Round 1
# (or a minimal fallback) instead of feeding the result back for another LLM turn.
# This saves ~8000 prompt tokens per skipped round.
#
# NOT in this set (require LLM to interpret results):
#   query_calendar_events, search_places, get_place_details, get_directions,
#   trigger_emergency, search_knowledge, list_reminders, draft_email,
#   summarize_pet_profile, list_pets
# Also excluded: plan, request_images (need continued loop execution)
SKIP_ROUND2_TOOLS = {
    "create_calendar_event",
    "create_pet",
    "update_pet_profile",
    "update_calendar_event",
    "delete_calendar_event",
    "delete_pet",
    "create_reminder",
    "update_reminder",
    "delete_reminder",
    "delete_all_reminders",
    "set_language",
    "set_pet_avatar",
    "upload_event_photo",
    "save_pet_profile_md",
    "manage_daily_task",
    "create_daily_task",
    "add_event_location",
    "remove_event_photo",
    "introduce_product",
}


async def maybe_await(fn, *args):
    """Call fn(*args), awaiting the result if it's a coroutine."""
    result = fn(*args)
    if asyncio.iscoroutine(result):
        return await result
    return result
