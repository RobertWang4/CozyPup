"""Confirmation gate for mutating tool calls."""

from __future__ import annotations

from typing import Any

from app.agents.confirm_cards import confirm_card_details
from app.agents.constants import needs_confirm
from app.agents.locale import t
from app.agents.tool_context import ToolDispatchContext
from app.agents.tool_invocation import ToolInvocation

WAITING_CONFIRM_INSTRUCTION = (
    "⚠️ 此操作【尚未执行】。系统已向用户弹出确认卡片，用户必须点击才会真正执行。"
    "你【绝对不能】告诉用户'已删除/已修改/已更新'——数据库完全没变。"
    "正确回复应该是：'已准备好，请在卡片上点击确认～'（用用户语言）。"
    "⚠️ THIS ACTION HAS NOT EXECUTED. A confirmation card was shown; the user must tap it. "
    "DO NOT say 'deleted/updated/saved' — the DB is unchanged. "
    "Say something like: 'Ready — please tap confirm on the card.'"
)


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    user_msgs = [
        m.get("content", "")
        for m in messages
        if m.get("role") == "user" and isinstance(m.get("content"), str)
    ]
    return user_msgs[-1] if user_msgs else ""


def describe_tool_call(
    fn_name: str,
    fn_args: dict,
    pets: list | None = None,
    lang: str = "zh",
    event_info: dict | None = None,
    image_urls: list[str] | None = None,
) -> str:
    """Generate human-readable description from LLM's tool call arguments."""
    def _pet_name(pid: str) -> str:
        if not pets:
            return ""
        for p in pets:
            if str(p.id if hasattr(p, "id") else p.get("id", "")) == pid:
                return p.name if hasattr(p, "name") else p.get("name", "")
        return ""

    def _label(name_str: str) -> str:
        if not name_str:
            return ""
        return f"「{name_str}」" if lang == "zh" else f"{name_str}'s"

    pid = fn_args.get("pet_id", "")
    name = _pet_name(pid)
    label = _label(name)

    if fn_name == "update_pet_profile":
        info = fn_args.get("info", {})
        if "name" in info:
            return t("desc_rename", lang).format(label=label, name=info["name"])
        from app.agents.tools.pets import _format_saved_fields
        fields = _format_saved_fields(info, lang)
        if fields:
            sep = "、" if lang == "zh" else ", "
            pairs = sep.join(f"{f['label']}: {f['value']}" for f in fields)
            return t("desc_update_pet", lang).format(label=label, keys=pairs)
        keys = ", ".join(info.keys())
        return t("desc_update_pet", lang).format(label=label, keys=keys)
    if fn_name == "create_pet":
        return t("desc_create_pet", lang).format(name=fn_args.get("name", ""))
    if fn_name == "delete_pet":
        return t("desc_delete_pet", lang).format(label=label)
    if fn_name == "create_calendar_event":
        title = fn_args.get("title", "")
        d = fn_args.get("event_date", "")
        if not label:
            pet_ids = fn_args.get("pet_ids") or []
            if pet_ids:
                label = _label(_pet_name(str(pet_ids[0])))
        meta_parts = []
        cost = fn_args.get("cost")
        if cost:
            meta_parts.append(f"${cost:g}" if isinstance(cost, (int, float)) else f"${cost}")
        ev_time = fn_args.get("event_time")
        if ev_time:
            meta_parts.append(str(ev_time))
        if image_urls:
            meta_parts.append(f"📷 {len(image_urls)} 张" if lang == "zh" else f"📷 {len(image_urls)}")
        if fn_args.get("reminder_at"):
            meta_parts.append("🔔")
        base = " ".join(
            t("desc_create_event", lang).format(label=label, title=title, date=d).split()
        )
        if meta_parts:
            sep = " · "
            base += (" （" + sep.join(meta_parts) + "）") if lang == "zh" else (" (" + sep.join(meta_parts) + ")")
        return base
    if fn_name in ("update_calendar_event", "delete_calendar_event"):
        if event_info and event_info.get("title"):
            ev_pet = event_info.get("pet_name") or ""
            ev_label = f"「{ev_pet}」" if lang == "zh" and ev_pet else f"{ev_pet}'s" if ev_pet else ""
            key = "desc_update_event" if fn_name == "update_calendar_event" else "desc_delete_event"
            return " ".join(t(key, lang).format(
                label=ev_label,
                title=event_info["title"],
                date=event_info.get("date", ""),
            ).split())
        key_generic = (
            "desc_update_event_generic" if fn_name == "update_calendar_event"
            else "desc_delete_event_generic"
        )
        return t(key_generic, lang)
    if fn_name == "create_reminder":
        return t("desc_create_reminder", lang).format(title=fn_args.get("title", ""))
    if fn_name == "update_reminder":
        return t("desc_update_reminder", lang)
    if fn_name == "delete_reminder":
        return t("desc_delete_reminder", lang)
    if fn_name == "delete_all_reminders":
        return t("desc_delete_all_reminders", lang)
    if fn_name == "manage_daily_task":
        action = fn_args.get("action", "")
        title = fn_args.get("title", "") or (fn_args.get("updates") or {}).get("title", "")
        if action == "delete_all":
            return t("desc_daily_task_delete_all", lang)
        if action == "delete":
            return t("desc_daily_task_delete", lang).format(title=title)
        if action == "deactivate":
            return t("desc_daily_task_deactivate", lang).format(title=title)
    if fn_name == "draft_email":
        return t("desc_draft_email", lang).format(subject=fn_args.get("subject", ""))
    if fn_name == "save_pet_profile_md":
        return t("desc_save_profile", lang).format(label=label)
    if fn_name == "set_pet_avatar":
        return t("desc_set_avatar", lang).format(label=label)
    if fn_name == "upload_event_photo":
        return t("desc_upload_photo", lang)
    if fn_name == "remove_event_photo":
        return "删除事件照片" if lang == "zh" else "Remove event photo"
    if fn_name == "create_daily_task":
        title = fn_args.get("title", "")
        return f"添加日常任务「{title}」" if lang == "zh" else f"Add daily task \"{title}\""
    if fn_name == "set_language":
        target = fn_args.get("language", "")
        target_label = {"zh": "中文", "en": "English"}.get(target, target)
        return f"切换语言为 {target_label}" if lang == "zh" else f"Switch language to {target_label}"
    return fn_name


async def lookup_event_info(db, user_id, event_id_raw, pets: list | None = None) -> dict | None:
    """Return {title, date, pet_name} for a calendar event, or None if not found."""
    import uuid as _uuid
    from sqlalchemy import select
    from app.models import CalendarEvent

    try:
        event_id = _uuid.UUID(str(event_id_raw))
    except (ValueError, TypeError):
        return None

    try:
        result = await db.execute(
            select(CalendarEvent).where(
                CalendarEvent.id == event_id,
                CalendarEvent.user_id == user_id,
            )
        )
        event = result.scalar_one_or_none()
    except Exception:
        return None

    if not event:
        return None

    pet_name = ""
    if pets and event.pet_id:
        pid_str = str(event.pet_id)
        for p in pets:
            if str(p.id if hasattr(p, "id") else p.get("id", "")) == pid_str:
                pet_name = p.name if hasattr(p, "name") else p.get("name", "")
                break

    return {
        "title": event.title,
        "date": event.event_date.isoformat() if event.event_date else "",
        "pet_name": pet_name,
    }


async def build_confirm_card(
    invocation: ToolInvocation,
    context: ToolDispatchContext,
    action_id: str,
) -> dict[str, Any] | None:
    """Return the `confirm_action` card for this call, or None if no confirm.

    Pure apart from one read-only `lookup_event_info` query, so the graph's
    confirm node can rebuild the identical card when LangGraph re-runs it
    after a resume.
    """
    if not context.session_id:
        return None

    fn_name = invocation.name
    fn_args = invocation.arguments
    last_user_text = _last_user_text(context.messages)
    if not needs_confirm(fn_name, fn_args, last_user_text):
        return None

    event_info = None
    if fn_name in {"delete_calendar_event", "update_calendar_event"} and fn_args.get("event_id"):
        event_info = await lookup_event_info(
            context.db,
            context.user_id,
            fn_args["event_id"],
            pets=context.pets,
        )

    effective_urls = context.image_urls or context.recent_image_urls
    desc = describe_tool_call(
        fn_name,
        fn_args,
        pets=context.pets,
        lang=context.lang,
        event_info=event_info,
        image_urls=effective_urls,
    )
    return {
        "type": "confirm_action",
        "action_id": action_id,
        "message": desc,
        **confirm_card_details(fn_name, fn_args, context.lang),
    }
