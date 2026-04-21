"""Unified Agent Loop — single orchestrator that replaced the old 4-path design.

One `while` loop handles every scenario (pure chat, single tool call, multi
tool call, image analysis). A `nudge` mechanism catches the case where the
LLM failed to call a high-confidence suggested tool and retries once.

Flow per round:
  1. Stream LLM completion (parallel non-streaming capture when trace is on)
  2. If tool_calls returned → dispatch each (validate → confirm gate →
     execute → emit card) → feed results back → loop
  3. If no tool_calls → check plan nag, then nudge, then exit

Key collaborators:
  - dispatch_tool: validates, gates, and executes a single tool call
  - constants.needs_confirm: central confirm-gate policy
  - micro_compact: compresses old tool results between rounds
  - trace_collector: optional per-request trace for X-Debug header
  - pre_processing.SuggestedAction: input to the nudge mechanism

Invariants:
  - MAX_ROUNDS caps the loop to prevent runaway tool chains
  - `needs_confirm` never consults the LLM — confirm decisions are
    deterministic so behavior is predictable
  - Tools in SKIP_ROUND2_TOOLS let us reuse Round 1 streaming text as the
    final response without another LLM call (saves ~8k prompt tokens)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Awaitable

import litellm

from app.agents import llm_extra_kwargs
from app.agents.constants import SKIP_ROUND2_TOOLS, maybe_await, needs_confirm
from app.agents.locale import t
from app.agents.micro_compact import micro_compact
from app.agents.pending_actions import store_action
from app.agents.pre_processing.types import SuggestedAction
from app.agents.tools import execute_tool, get_tool_definitions
from app.agents.trace_collector import TraceCollector, INACTIVE_TRACE
from app.agents.validation import validate_tool_args
from app.config import settings

logger = logging.getLogger(__name__)

MAX_ROUNDS = 5            # Max loop iterations, including nudge/plan-nag retries
NUDGE_CONFIDENCE = 0.8    # Minimum pre-processor confidence to trigger a nudge


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class OrchestratorResult:
    """Aggregate result of one `run_orchestrator` call.

    Streams are emitted live via on_token/on_card callbacks; this struct
    exists so the caller can also inspect final state (e.g. to persist the
    assistant message, emit debug trace, or bill tokens).
    """
    response_text: str = ""
    cards: list[dict] = field(default_factory=list)
    confirm_cards: list[dict] = field(default_factory=list)
    tools_called: set[str] = field(default_factory=set)
    # Tools that actually executed (not deferred behind a confirm card and
    # not an error). Used by the write-claim nag so a confirm-pending delete
    # doesn't count as a real write.
    tools_executed: set[str] = field(default_factory=set)
    plan_steps: list[dict] = field(default_factory=list)  # Steps from plan() tool
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    model_used: str = ""


# ---------------------------------------------------------------------------
# _describe_tool_call — human-readable summary shown on confirm cards
# ---------------------------------------------------------------------------

def _describe_tool_call(
    fn_name: str,
    fn_args: dict,
    pets: list | None = None,
    lang: str = "zh",
    event_info: dict | None = None,
    image_urls: list[str] | None = None,
) -> str:
    """Generate human-readable description from LLM's tool call arguments.

    event_info (optional) is looked up from DB for delete/update_calendar_event
    so the confirm card can show which event is being modified.
    image_urls (optional) is used to show "(1 张图片)" on create_calendar_event
    confirm cards.
    """
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
            return t("desc_rename", lang).format(label=label, name=info['name'])
        from app.agents.tools.pets import _format_saved_fields
        fields = _format_saved_fields(info, lang)
        if fields:
            sep = "、" if lang == "zh" else ", "
            pairs = sep.join(f"{f['label']}: {f['value']}" for f in fields)
            return t("desc_update_pet", lang).format(label=label, keys=pairs)
        keys = ", ".join(info.keys())
        return t("desc_update_pet", lang).format(label=label, keys=keys)
    if fn_name == "create_pet":
        return t("desc_create_pet", lang).format(name=fn_args.get('name', ''))
    if fn_name == "delete_pet":
        return t("desc_delete_pet", lang).format(label=label)
    if fn_name == "create_calendar_event":
        title = fn_args.get("title", "")
        d = fn_args.get("event_date", "")
        # multi-pet: label uses first pet_ids entry if pet_id absent
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
            if lang == "zh":
                meta_parts.append(f"📷 {len(image_urls)} 张")
            else:
                meta_parts.append(f"📷 {len(image_urls)}")
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
            if lang == "zh":
                ev_label = f"「{ev_pet}」" if ev_pet else ""
            else:
                ev_label = f"{ev_pet}'s" if ev_pet else ""
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
        return t("desc_create_reminder", lang).format(title=fn_args.get('title', ''))
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
        return t("desc_draft_email", lang).format(subject=fn_args.get('subject', ''))
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
        return (f"添加日常任务「{title}」" if lang == "zh"
                else f"Add daily task \"{title}\"")
    if fn_name == "set_language":
        target = fn_args.get("language", "")
        target_label = {"zh": "中文", "en": "English"}.get(target, target)
        return (f"切换语言为 {target_label}" if lang == "zh"
                else f"Switch language to {target_label}")
    if fn_name == "manage_daily_task":
        title = fn_args.get("title", "") or (fn_args.get("updates") or {}).get("title", "")
        action = fn_args.get("action", "")
        return (f"更新日常任务「{title}」({action})" if lang == "zh"
                else f"Update daily task \"{title}\" ({action})")
    return fn_name


# ---------------------------------------------------------------------------
# _lookup_event_info — fetch event display fields for confirm cards
# ---------------------------------------------------------------------------

async def _lookup_event_info(db, user_id, event_id_raw, pets: list | None = None) -> dict | None:
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


# ---------------------------------------------------------------------------
# _load_images_from_urls — read historical photos from disk as base64
# ---------------------------------------------------------------------------

def _load_images_from_urls(urls: list[str]) -> list[str]:
    """Load photos referenced by earlier messages and encode as base64.

    Used by request_images when the current turn has no new attachments
    but the user is asking about a picture from a prior message.

    URLs are of the form /api/v1/calendar/photos/{uuid}.jpg mapped to
    PHOTO_DIR on disk. Files larger than 5 MB are skipped (LLM image cap).
    """
    import base64
    from pathlib import Path

    photo_dir = (
        Path("/app/uploads/photos") if Path("/app/uploads").exists()
        else Path(__file__).resolve().parent.parent / "uploads" / "photos"
    )
    result = []
    for url in urls:
        filename = url.rsplit("/", 1)[-1]
        filepath = photo_dir / filename
        try:
            if filepath.exists() and filepath.stat().st_size <= 5 * 1024 * 1024:
                result.append(base64.b64encode(filepath.read_bytes()).decode())
        except Exception:
            continue
    return result


# ---------------------------------------------------------------------------
# dispatch_tool — unified tool pipeline: validate → confirm → execute → card
# ---------------------------------------------------------------------------

async def dispatch_tool(
    tool_call: dict,
    db,
    user_id,
    session_id,
    result: OrchestratorResult,
    on_card: Callable | None,
    lang: str,
    pets: list | None = None,
    images: list[str] | None = None,
    image_urls: list[str] | None = None,
    recent_image_urls: list[str] | None = None,
    **kwargs,
) -> dict:
    """Unified tool execution entry point.

    Always returns a dict (never None, never raises to the caller).
    - Validation failure → {"error": "..."} — LLM sees the error next round
      and self-corrects without any extra prompt engineering.
    - Confirm gate hit → {"status": "waiting_confirm", "message": "..."}
      — a confirm card is emitted and the tool is stored in pending_actions.
    - Normal execution → the handler's result dict (may contain `card`).

    Side effects:
      - May emit a card via on_card callback.
      - Commits the DB transaction on success (tools flush to DB then this
        fn commits so the router sees persisted state).
      - Appends to result.cards / result.confirm_cards / result.tools_called.
    """
    fn_name = tool_call["function"]["name"]

    try:
        fn_args = json.loads(tool_call["function"]["arguments"])
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid JSON arguments: {exc}"}

    result.tools_called.add(fn_name)

    # Guard: LLM sometimes invents events for pets the user did not mention
    # (e.g. user says "Vinnie ate" but LLM creates one for Huahua too).
    # Block the call server-side — cheaper + more reliable than prompting harder.
    if fn_name == "create_calendar_event" and fn_args.get("pet_id") and pets:
        user_msgs = [m.get("content", "") for m in kwargs.get("_messages", []) if m.get("role") == "user" and isinstance(m.get("content"), str)]
        last_user = user_msgs[-1] if user_msgs else ""
        # Find which pets are mentioned by name
        mentioned_pet_ids = set()
        for p in pets:
            pname = p.name if hasattr(p, "name") else p.get("name", "")
            pid = str(p.id if hasattr(p, "id") else p.get("id", ""))
            if pname and pname.lower() in last_user.lower():
                mentioned_pet_ids.add(pid)
        # If user mentioned specific pet(s) but this call is for an unmentioned pet, block it
        if mentioned_pet_ids and fn_args["pet_id"] not in mentioned_pet_ids:
            blocked_name = ""
            for p in pets:
                pid = str(p.id if hasattr(p, "id") else p.get("id", ""))
                if pid == fn_args["pet_id"]:
                    blocked_name = p.name if hasattr(p, "name") else p.get("name", "")
            logger.info("pet_mismatch_blocked", extra={
                "blocked_pet": blocked_name,
                "mentioned": list(mentioned_pet_ids),
                "user_text": last_user[:60],
            })
            return {"success": False, "error": f"用户只提到了特定的宠物，没有提到{blocked_name}。请只为用户提到的宠物创建事件。"}

    # Guard: refuse to create a second pet with the same name as an existing
    # one (case-insensitive). Duplicate creation is a classic LLM failure
    # mode; the error message steers the LLM to update_pet_profile instead.
    if fn_name == "create_pet" and fn_args.get("name") and pets:
        new_name = str(fn_args["name"]).strip().lower()
        for p in pets:
            existing_name = (p.name if hasattr(p, "name") else p.get("name", "")) or ""
            existing_id = str(p.id if hasattr(p, "id") else p.get("id", ""))
            if existing_name.strip().lower() == new_name:
                logger.info("duplicate_pet_blocked", extra={
                    "name": new_name,
                    "existing_id": existing_id,
                })
                return {
                    "success": False,
                    "error": (
                        f"宠物「{existing_name}」已经存在 (id={existing_id})。"
                        f"不要重复创建 — 如需补充信息，请改用 update_pet_profile 并传 pet_id。"
                    ),
                }

    # Best-effort cost backfill: LLM frequently forgets to extract the
    # amount the user mentioned. Regex-extract so the calendar event has it.
    if fn_name == "create_calendar_event" and fn_args.get("cost") is None:
        import re
        user_msgs = [m.get("content", "") for m in kwargs.get("_messages", []) if m.get("role") == "user" and isinstance(m.get("content"), str)]
        last_user = user_msgs[-1] if user_msgs else ""
        # Match: 花了300/花了300块/花了100/300元/cost 50
        cost_match = re.search(r"花了?\s*(\d+(?:\.\d+)?)\s*[块元刀]?|(\d+(?:\.\d+)?)\s*[块元刀]", last_user)
        if cost_match:
            amount = float(cost_match.group(1) or cost_match.group(2))
            fn_args["cost"] = amount
            tool_call["function"]["arguments"] = json.dumps(fn_args, ensure_ascii=False)
            logger.info("cost_auto_fixed", extra={"extracted": amount, "user_text": last_user[:60]})

    # Best-effort end_date backfill: LLM often omits end_date when the user
    # said "for the next 7 days" or "until April 10", silently turning a
    # bounded task into a permanent one. Regex-extract common phrasings.
    if fn_name == "create_daily_task" and not fn_args.get("end_date"):
        import re
        from datetime import date as _date, timedelta as _td
        user_msgs = [m.get("content", "") for m in kwargs.get("_messages", []) if m.get("role") == "user" and isinstance(m.get("content"), str)]
        last_user = user_msgs[-1] if user_msgs else ""
        today = _date.today()
        extracted_end = None

        # "到4月10号" / "到4月10日"
        m = re.search(r"到(\d{1,2})月(\d{1,2})[号日]", last_user)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            year = today.year if month >= today.month else today.year + 1
            try:
                extracted_end = _date(year, month, day)
            except ValueError:
                pass

        # "到下周日" / "到下周六" etc
        if not extracted_end:
            m = re.search(r"到?下周([一二三四五六日天])", last_user)
            if m:
                weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
                target_wd = weekday_map.get(m.group(1), 6)
                days_ahead = (target_wd - today.weekday()) % 7 + 7  # next week
                extracted_end = today + _td(days=days_ahead)

        # "接下来7天" / "接下来N天"
        if not extracted_end:
            m = re.search(r"接下来(\d+)天", last_user)
            if m:
                extracted_end = today + _td(days=int(m.group(1)))

        # "这周" / "本周"
        if not extracted_end and re.search(r"[这本]周", last_user):
            days_to_sunday = 6 - today.weekday()
            extracted_end = today + _td(days=max(days_to_sunday, 1))

        if extracted_end:
            fn_args["end_date"] = extracted_end.isoformat()
            # Rewrite the tool_call arguments so execute_tool sees the fix
            tool_call["function"]["arguments"] = json.dumps(fn_args, ensure_ascii=False)
            logger.info("end_date_auto_fixed", extra={
                "extracted": extracted_end.isoformat(),
                "user_text": last_user[:60],
            })

    # plan tool is purely control-flow (LLM declares the decomposition) — it
    # does not touch the DB. We just record the steps so the plan-nag check
    # in the main loop knows what to wait for.
    if fn_name == "plan":
        steps = fn_args.get("steps", [])
        result.plan_steps = steps
        step_summary = "; ".join(f"[{s.get('id')}] {s.get('action')}" for s in steps)
        return {
            "status": "planned",
            "message": f"已规划 {len(steps)} 个步骤: {step_summary}",
            "steps": steps,
        }

    # request_images returns a sentinel (_inject_images) that the main loop
    # reads and turns into a proper multimodal user message before the next
    # round, so the LLM actually sees the pixels.
    if fn_name == "request_images":
        if images:
            return {
                "status": "images_loaded",
                "message": "图片已加载" if lang == "zh" else "Images loaded",
                "_inject_images": images,
            }
        # No new images this turn — fall back to photos from recent messages
        if recent_image_urls:
            history_images = _load_images_from_urls(recent_image_urls)
            if history_images:
                return {
                    "status": "images_loaded",
                    "message": ("已加载历史消息中的图片" if lang == "zh"
                                else "Loaded images from previous messages"),
                    "_inject_images": history_images,
                }
        return {"error": "用户没有附带图片" if lang == "zh" else "No images attached"}

    # Confirm gate: always-confirm tools + mutating tools without an explicit
    # action verb in the user's message get a confirm card instead of
    # executing. The tool call is persisted in pending_actions so a later
    # /confirm endpoint can replay it once the user taps confirm.
    user_msgs = [m.get("content", "") for m in kwargs.get("_messages", []) if m.get("role") == "user" and isinstance(m.get("content"), str)]
    last_user_text = user_msgs[-1] if user_msgs else ""
    if needs_confirm(fn_name, fn_args, last_user_text) and session_id:
        event_info = None
        if fn_name in {"delete_calendar_event", "update_calendar_event"} and fn_args.get("event_id"):
            event_info = await _lookup_event_info(db, user_id, fn_args["event_id"], pets=pets)
        effective_urls = image_urls or recent_image_urls
        desc = _describe_tool_call(
            fn_name, fn_args, pets=pets, lang=lang,
            event_info=event_info, image_urls=effective_urls,
        )
        # Persist image_urls inside the stored args so the confirm endpoint
        # can re-run the tool with the original photos attached — otherwise
        # the photos would be gone by the time the user taps confirm.
        stored_args = dict(fn_args)
        if effective_urls and fn_name == "create_calendar_event":
            stored_args["_image_urls"] = list(effective_urls)
        action_id = await store_action(
            db=db, user_id=str(user_id), session_id=str(session_id),
            tool_name=fn_name, arguments=stored_args, description=desc,
        )
        card = {"type": "confirm_action", "action_id": action_id, "message": desc}
        result.confirm_cards.append(card)
        if on_card:
            await maybe_await(on_card, card)
        # Strongly-worded result so the LLM does NOT claim completion. grok-4-1
        # has a tendency to say "已删除" after seeing any status field — we beef
        # this up with explicit anti-fabrication instructions.
        return {
            "status": "waiting_confirm",
            "executed": False,
            "db_changed": False,
            "instruction_for_assistant": (
                "⚠️ 此操作【尚未执行】。系统已向用户弹出确认卡片，用户必须点击才会真正执行。"
                "你【绝对不能】告诉用户'已删除/已修改/已更新'——数据库完全没变。"
                "正确回复应该是：'已准备好，请在卡片上点击确认～'（用用户语言）。"
                "⚠️ THIS ACTION HAS NOT EXECUTED. A confirmation card was shown; the user must tap it. "
                "DO NOT say 'deleted/updated/saved' — the DB is unchanged. "
                "Say something like: 'Ready — please tap confirm on the card.'"
            ),
            "description": desc,
        }

    # --- Validate ---
    errors = validate_tool_args(fn_name, fn_args)
    if errors:
        return {"error": "; ".join(errors)}

    # --- Execute ---
    try:
        # Pass image_urls/location/lang to every handler; handlers that don't
        # need them simply accept **kwargs and ignore the extras.
        exec_kwargs = {"lang": lang}
        if "location" in kwargs:
            exec_kwargs["location"] = kwargs["location"]
        # Prefer current-turn photos; fall back to photos from recent messages
        # so follow-up messages ("attach THIS one too") still work.
        effective_image_urls = image_urls or recent_image_urls
        if effective_image_urls:
            exec_kwargs["image_urls"] = effective_image_urls

        tool_result = await execute_tool(fn_name, fn_args, db, user_id, **exec_kwargs)
        await db.commit()
        # Mark as truly executed only when the handler reports success. This
        # is what the write-claim nag consults — confirm-pending and errored
        # calls don't count.
        if tool_result.get("success"):
            result.tools_executed.add(fn_name)
    except Exception as exc:
        logger.error("dispatch_tool_error", extra={
            "tool": fn_name, "error": str(exc)[:300],
        })
        return {"error": str(exc)[:200]}

    # Keep RAG embeddings in sync with calendar_event writes.
    if tool_result.get("success") and tool_result.get("event_id"):
        from app.rag.event_sync import (
            schedule_event_embedding,
            schedule_event_embedding_delete,
        )
        if fn_name in ("create_calendar_event", "update_calendar_event"):
            schedule_event_embedding(tool_result["event_id"])
        elif fn_name == "delete_calendar_event":
            schedule_event_embedding_delete(tool_result["event_id"])

    # Some handlers (e.g. gender/species first-time set) run a partial update
    # and then return needs_confirm=True for the lockable portion. Surface
    # a confirm card for that leftover piece.
    if tool_result.get("needs_confirm") and session_id:
        confirm_tool = tool_result.get("confirm_tool", fn_name)
        confirm_args = tool_result.get("confirm_arguments", fn_args)
        confirm_desc = tool_result.get("confirm_description", f"确认执行 {fn_name}")
        action_id = await store_action(
            db=db, user_id=str(user_id), session_id=str(session_id),
            tool_name=confirm_tool, arguments=confirm_args, description=confirm_desc,
        )
        card = {"type": "confirm_action", "action_id": action_id, "message": confirm_desc}
        result.confirm_cards.append(card)
        if on_card:
            await maybe_await(on_card, card)
        return tool_result

    # --- Emit card ---
    card = tool_result.get("card")
    if card:
        result.cards.append(card)
        if on_card:
            await maybe_await(on_card, card)

    return tool_result


# ---------------------------------------------------------------------------
# Nudge helpers — retry once when LLM skipped a high-confidence tool
# ---------------------------------------------------------------------------

def _find_missed_tools(
    suggested_actions: list[SuggestedAction],
    tools_called: set[str],
) -> list[SuggestedAction]:
    """Return high-confidence suggestions the LLM didn't call.

    Only tools in NUDGE_TOOLS are ever forced (search_places,
    trigger_emergency, set_language — the ones the LLM reliably forgets).
    All other pre-processor suggestions are advisory; don't nudge on them.
    """
    from app.agents.constants import NUDGE_TOOLS
    return [
        a for a in suggested_actions
        if a.confidence >= NUDGE_CONFIDENCE
        and a.tool_name not in tools_called
        and a.tool_name in NUDGE_TOOLS
    ]


def _inject_nudge(
    messages: list[dict],
    last_text: str,
    missed: list[SuggestedAction],
    lang: str,
) -> None:
    """Inject a nudge message so the LLM calls the missed tool next round."""
    # Preserve last round's text as an assistant turn so the conversation
    # reads coherently to the LLM (otherwise it sees a stray user message).
    if last_text:
        messages.append({"role": "assistant", "content": last_text})

    hints = []
    for a in missed:
        hints.append(f"- {a.tool_name}({json.dumps(a.arguments, ensure_ascii=False)})")

    if lang == "zh":
        nudge_text = (
            "你的回复没有调用工具。根据用户意图分析，你应该调用以下工具：\n"
            + "\n".join(hints)
            + "\n请立即调用对应的工具。不要用文字假装操作已完成。"
        )
    else:
        nudge_text = (
            "Your response did not call any tools. Based on intent analysis, you should call:\n"
            + "\n".join(hints)
            + "\nPlease call the appropriate tools now. Do not pretend the action was completed."
        )

    messages.append({"role": "user", "content": nudge_text})


# ---------------------------------------------------------------------------
# Write-claim guard — catch LLM hallucinating "已更新/已删除" without a write
# ---------------------------------------------------------------------------

# All tools that actually mutate persisted state. If the LLM's text claims a
# mutation happened but none of these were called, it's a fabrication.
_WRITE_TOOLS: set[str] = {
    "create_calendar_event", "update_calendar_event", "delete_calendar_event",
    "create_reminder", "update_reminder", "delete_reminder", "delete_all_reminders",
    "create_pet", "delete_pet", "update_pet_profile",
    "save_pet_profile_md", "summarize_pet_profile",
    "create_daily_task", "manage_daily_task",
    "set_pet_avatar", "upload_event_photo", "remove_event_photo",
    "add_event_location", "set_language",
}

# Completed-action phrases that indicate the LLM claims a write happened.
# Keep these narrow — they should only match past-tense success claims,
# not user requests or future-tense descriptions.
_WRITE_CLAIM_ZH = re.compile(
    r"已(?:更新|改为|改成|修改|删除|记录|保存|添加|创建|设置|关联|附加|修正|取消|清空)"
    r"|(?:更新|修改|删除|记录|保存|添加|修正|调整)好了"
    r"|(?:改好了|改成了|删掉了|记下了|记好了|设好了|存好了|加上了|附上了|挪到了|移到了)"
)
_WRITE_CLAIM_EN = re.compile(
    r"\b(?:updated|changed (?:it |the [^ ]+ )?to|deleted|removed|recorded|saved|added|created|modified|attached|cleared|canceled|cancelled|set it to|renamed)\b",
    re.IGNORECASE,
)


def _text_claims_write(text: str, lang: str) -> bool:
    """True if the reply text claims a mutation that we should verify happened."""
    if not text:
        return False
    if lang == "zh":
        return bool(_WRITE_CLAIM_ZH.search(text))
    return bool(_WRITE_CLAIM_EN.search(text))


# User disagreement / pushback phrases. When the latest user message matches,
# we suspect the LLM's prior chat turns have fabricated a completion, and
# inject a strong "trust the DB, not chat history" directive before the loop.
_PUSHBACK_ZH = re.compile(
    r"你没(?:删|改|更新|保存|做|执行)"
    r"|没删(?:掉|啊|呢|嘛)?|没改(?:掉|啊|呢)?|没更新|没生效|没执行"
    r"|明明还在|还在啊|还(?:存在|有)呢|没反应"
    r"|再(?:查|看|试|检查)一[下眼次]"
    r"|你好好(?:看|查)"
    r"|你看一下|你看看"
    r"|骗人|瞎说|撒谎"
)
_PUSHBACK_EN = re.compile(
    r"\b(?:you didn'?t|didn'?t actually|not deleted|not removed|still (?:there|exists|showing)|"
    r"nothing happened|check again|look again|try again|liar|lying|fake)\b",
    re.IGNORECASE,
)


def _detect_pushback(text: str, lang: str) -> bool:
    """True if the user's latest message disputes a prior completion claim."""
    if not text:
        return False
    if lang == "zh":
        return bool(_PUSHBACK_ZH.search(text))
    # Be lenient: either regex may catch bilingual users
    return bool(_PUSHBACK_EN.search(text) or _PUSHBACK_ZH.search(text))


def _inject_pushback_preamble(messages: list[dict], lang: str) -> None:
    """Append a high-priority system directive just before the final user turn.

    The LLM's own prior '已删除/updated' statements in chat history are
    unreliable — they may be fabrications from rounds where no write tool
    actually executed. This preamble tells the LLM to ignore them and
    re-verify against the DB by calling tools fresh.
    """
    if lang == "zh":
        note = (
            "⚠️【系统强制指令 — 最高优先级】用户正在反驳你之前的操作声明。\n"
            "你之前在对话里说过的'已删除/已更新/已修改/已保存'【可能是编造的】——"
            "很多轮你只调了查询工具就凭空说'完成了'，数据库根本没变。\n"
            "现在：\n"
            "1. 【忽略】对话历史里所有'已X'的声明。它们不是事实。\n"
            "2. 【必须】立刻调用查询工具（query_calendar_events / list_reminders / list_pets 等）重新查真实 DB 状态。\n"
            "3. 如果 DB 里东西还在，立刻调用对应的写工具（delete_calendar_event / update_* 等）真正执行。\n"
            "4. 只有写工具返回 success=True 后，才能告诉用户'已删除/已更新'。\n"
            "5. 如果是 waiting_confirm，告诉用户'请点击卡片确认'，不是'已完成'。"
        )
    else:
        note = (
            "⚠️ [SYSTEM OVERRIDE — HIGHEST PRIORITY] The user is disputing a prior completion claim.\n"
            "Your earlier 'deleted/updated/saved' statements in this chat history MAY BE FABRICATIONS — "
            "in several rounds you only called query tools yet claimed completion. The DB was never changed.\n"
            "Now:\n"
            "1. IGNORE every past 'done/deleted/updated' claim in the chat history. Do not trust them.\n"
            "2. IMMEDIATELY call a fresh query tool (query_calendar_events / list_reminders / list_pets / etc.) to see real DB state.\n"
            "3. If the item still exists in DB, IMMEDIATELY call the corresponding write tool (delete_* / update_*) to actually execute.\n"
            "4. Only after the write tool returns success=True may you tell the user it's done.\n"
            "5. If it returns waiting_confirm, tell the user to tap the confirm card — do NOT say 'done'."
        )
    messages.append({"role": "system", "content": note})


def _inject_write_claim_nag(
    messages: list[dict],
    last_text: str,
    lang: str,
) -> None:
    """Nag the LLM when it claimed a write but didn't call any write tool."""
    if last_text:
        messages.append({"role": "assistant", "content": last_text})
    if lang == "zh":
        nag = (
            "⚠️ 严重错误：你的回复声称已经更新/删除/修改了数据，但你这一轮和上一轮都【没有调用任何写工具】"
            "（update_calendar_event / delete_calendar_event / update_pet_profile / update_reminder / manage_daily_task 等）。\n"
            "查询工具（query_calendar_events / list_reminders / list_daily_tasks）【不会修改数据】。\n"
            "必须立刻调用对应的写工具完成用户要求的操作。不要再用文字假装。"
        )
    else:
        nag = (
            "⚠️ CRITICAL: Your reply claimed the data was updated/deleted/modified, but you did NOT call any write tool "
            "this turn or the previous turn (update_calendar_event / delete_calendar_event / update_pet_profile / "
            "update_reminder / manage_daily_task, etc.).\n"
            "Query tools (query_calendar_events / list_reminders / list_daily_tasks) do NOT modify data.\n"
            "Call the correct write tool NOW to actually perform the change. Do not fabricate completion again."
        )
    messages.append({"role": "user", "content": nag})


# ---------------------------------------------------------------------------
# _stream_completion — streaming LLM call (with optional trace capture)
# ---------------------------------------------------------------------------

async def _capture_non_streaming(
    messages: list[dict],
    model: str,
    lang: str,
    round_num: int,
    trace: TraceCollector,
):
    """Parallel non-streaming call to capture the full chat.completion JSON."""
    try:
        import asyncio
        response = await asyncio.wait_for(
            litellm.acompletion(
                model=model,
                messages=messages,
                tools=get_tool_definitions(lang),
                tool_choice="auto",
                temperature=0.3,
                stream=False,
                drop_params=True,
                **llm_extra_kwargs(),
            ),
            timeout=60,
        )
        # Convert litellm response to dict
        raw = response.model_dump() if hasattr(response, "model_dump") else response.to_dict() if hasattr(response, "to_dict") else {"raw": str(response)}
        trace.record_llm_response(round_num, raw)
    except Exception as exc:
        trace.record(f"llm_capture_error_round_{round_num}", str(exc)[:300])


async def _stream_completion(
    messages: list[dict],
    model: str,
    on_token: Callable | None = None,
    lang: str = "zh",
    trace: TraceCollector = INACTIVE_TRACE,
    round_num: int = 0,
) -> tuple[str, list[dict], dict]:
    """Stream the LLM response and return (text, tool_calls, usage).

    When trace is active a parallel non-streaming call also runs so the
    admin trace view gets the full raw JSON (streaming deltas are lossy).
    Retries up to 2 times on transport errors.
    """
    import asyncio

    text_parts = []
    tool_calls_map = {}
    usage = {}

    # If trace is active, fire parallel non-streaming call to capture full JSON
    capture_task = None
    if trace.active:
        capture_task = asyncio.create_task(
            _capture_non_streaming(messages, model, lang, round_num, trace)
        )

    max_retries = 2
    for attempt in range(max_retries):
        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                tools=get_tool_definitions(lang),
                tool_choice="auto",
                temperature=0.3,
                stream=True,
                stream_options={"include_usage": True},
                drop_params=True,
                **llm_extra_kwargs(),
            )

            async for chunk in response:
                delta = chunk.choices[0].delta

                if delta.content:
                    # Filter out LLM XML tag leaks (e.g. Grok outputs <parameter>, <xai:function_call>)
                    chunk_text = delta.content
                    if "<" in chunk_text and ("parameter" in chunk_text or "xai:" in chunk_text or "function_call" in chunk_text):
                        chunk_text = re.sub(r"</?(?:parameter|xai:?\w*|function_call)[^>]*>", "", chunk_text)
                    if chunk_text.strip():
                        text_parts.append(chunk_text)
                        if on_token:
                            await maybe_await(on_token, chunk_text)
                    else:
                        text_parts.append(delta.content)  # keep original for tool parsing

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {
                                "id": tc_delta.id or "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        tc = tool_calls_map[idx]
                        if tc_delta.id:
                            tc["id"] = tc_delta.id
                        if tc_delta.function and tc_delta.function.name:
                            tc["function"]["name"] += tc_delta.function.name
                        if tc_delta.function and tc_delta.function.arguments:
                            tc["function"]["arguments"] += tc_delta.function.arguments

                # Capture usage from final chunk (provider-dependent)
                if hasattr(chunk, "usage") and chunk.usage:
                    u = chunk.usage
                    usage = {
                        "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                        "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                    }

            break  # success, exit retry loop

        except Exception as exc:
            logger.error("stream_completion_error", extra={
                "error": str(exc)[:300],
                "attempt": attempt + 1,
                "max_retries": max_retries,
            })
            if attempt < max_retries - 1:
                # Reset state for retry — clear any partial text/tools from failed attempt
                text_parts.clear()
                tool_calls_map.clear()
                import asyncio as _asyncio
                await _asyncio.sleep(1)  # brief pause before retry
                logger.info("stream_completion_retry", extra={"attempt": attempt + 2})
                continue
            # Final attempt failed — give up
            if capture_task:
                capture_task.cancel()
            return "".join(text_parts), [], {}

    # Wait for capture task to finish (don't block too long)
    if capture_task:
        try:
            await asyncio.wait_for(capture_task, timeout=30)
        except (asyncio.TimeoutError, Exception):
            pass  # Capture is best-effort

    return "".join(text_parts), [tool_calls_map[i] for i in sorted(tool_calls_map)], usage


# ---------------------------------------------------------------------------
# Skip Round 2 — reuse Round 1 text as the final reply for simple CRUD tools
# ---------------------------------------------------------------------------

def _can_skip_round2(
    tool_calls: list[dict],
    tool_results_map: dict[str, dict],
    result: OrchestratorResult,
    round_text: str,
) -> bool:
    """Check if we can skip the next LLM round after tool execution.

    Conditions (ALL must be true):
    1. LLM produced text in this round (used as the response)
    2. All tools in this round are in SKIP_ROUND2_TOOLS
    3. No tool returned an error (errors need LLM to explain/retry)
    4. No images were injected (need LLM to analyze them)
    5. No pending plan steps (need to continue executing)
    """
    # Must have streaming text from Round 1 to use as response
    if not round_text or not round_text.strip():
        return False

    tool_names = {tc["function"]["name"] for tc in tool_calls}

    # All tools must be in the skip set
    if not tool_names.issubset(SKIP_ROUND2_TOOLS):
        return False

    # No errors — if any tool failed, LLM needs to see the error and retry/explain
    for name, tr in tool_results_map.items():
        if tr.get("error"):
            return False

    # No image injection (request_images needs LLM to interpret)
    for tr in tool_results_map.values():
        if "_inject_images" in tr:
            return False

    # No unfinished plan steps
    if result.plan_steps:
        planned_tools = {s["tool"] for s in result.plan_steps}
        executed = result.tools_called - {"plan"}
        if planned_tools - executed:
            return False

    return True


# ---------------------------------------------------------------------------
# run_orchestrator — unified Agent Loop entry point
# ---------------------------------------------------------------------------

async def run_orchestrator(
    message: str,
    system_prompt: str,
    context_messages: list[dict],
    model: str | None = None,
    db=None,
    user_id=None,
    session_id=None,
    on_token: Callable[[str], Awaitable[None]] | None = None,
    on_card: Callable[[dict], Awaitable[None]] | None = None,
    today: str = "",
    suggested_actions: list[SuggestedAction] | None = None,
    trace: TraceCollector = INACTIVE_TRACE,
    **kwargs,
) -> OrchestratorResult:
    """Run the unified agent loop until exhaustion or MAX_ROUNDS.

    Handles every chat scenario in one loop:
      - Pure chat: LLM emits text without tool_calls → exit immediately.
      - Single/multi tool: LLM emits tool_calls → dispatch each → feed
        results back → loop until LLM stops calling tools.
      - Image analysis: request_images injects base64 images via a special
        user message in the next round.
      - Nudge: if LLM skipped a NUDGE_TOOLS call that pre-processing was
        confident about, retry once with an explicit instruction.
      - Plan nag: if plan() was called but some planned tools never fired,
        nag the LLM to finish them.

    Streams tokens via on_token and cards via on_card. The returned
    OrchestratorResult also contains the aggregate state.
    """
    from app.debug.trace_logger import trace_log

    lang = kwargs.pop("lang", "zh")
    result = OrchestratorResult()
    use_model = model or settings.model
    result.model_used = use_model

    # Seed the message list with system prompt + recent history
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(context_messages)

    # Pushback defense: if the user's latest turn disputes a prior completion
    # claim, inject a high-priority system note so the LLM ignores its own
    # fabricated chat history and re-verifies against the DB.
    latest_user_text = ""
    for m in reversed(context_messages):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                latest_user_text = c
            elif isinstance(c, list):
                latest_user_text = " ".join(
                    part.get("text", "") for part in c if isinstance(part, dict)
                )
            break
    if _detect_pushback(latest_user_text, lang):
        _inject_pushback_preamble(messages, lang)
        logger.info("pushback_preamble_injected", extra={
            "user_text_sample": latest_user_text[:120],
        })

    text_parts: list[str] = []
    nudge_used = False
    plan_nag_used = False
    write_claim_nag_used = False

    # Extract dispatch_tool kwargs up front so they're not forwarded to the LLM
    images = kwargs.pop("images", None)
    image_urls = kwargs.pop("image_urls", None)
    recent_image_urls = kwargs.pop("recent_image_urls", None)  # photos from prior messages
    location = kwargs.pop("location", None)
    pets = kwargs.pop("pets", None)

    for round_num in range(MAX_ROUNDS):
        # Compress older tool_result payloads to save prompt tokens — keep
        # only the most recent round's full results.
        if round_num > 0:
            micro_compact(messages)

        # Stream the LLM response
        round_text, tool_calls, usage = await _stream_completion(
            messages, use_model, on_token, lang=lang,
            trace=trace, round_num=round_num,
        )

        # Accumulate token usage
        result.total_prompt_tokens += usage.get("prompt_tokens", 0)
        result.total_completion_tokens += usage.get("completion_tokens", 0)

        # Log LLM request
        trace_log("llm_request", round=round_num, data={
            "model": use_model,
            "message_count": len(messages),
            "messages_preview": [
                {"role": m["role"], "content": (m.get("content") or "")[:200]}
                for m in messages[-3:]
            ],
        })

        # Log LLM response
        trace_log("llm_response", round=round_num, data={
            "model": use_model,
            "text_length": len(round_text),
            "text_preview": round_text[:300] if round_text else "",
            "content": round_text or "",     # NEW — full content for admin trace
            "tool_calls": [
                {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}
                for tc in tool_calls
            ] if tool_calls else [],
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0),
        })

        # No tool_calls this round — decide: plan nag → nudge → exit
        if not tool_calls:
            text_parts.append(round_text)

            # Plan nag: if plan() declared steps but the LLM stopped before
            # executing all of them, inject a nag message and retry once.
            if not plan_nag_used and result.plan_steps:
                planned_tools = {s["tool"] for s in result.plan_steps}
                # Exclude plan itself when checking what still needs to run
                executed_tools = result.tools_called - {"plan"}
                missing_tools = planned_tools - executed_tools
                if missing_tools:
                    plan_nag_used = True
                    missing_steps = [s for s in result.plan_steps if s["tool"] in missing_tools]
                    trace.record("plan_nag_triggered", {
                        "round": round_num,
                        "missing_tools": list(missing_tools),
                        "missing_steps": missing_steps,
                    })
                    logger.info("plan_nag_triggered", extra={
                        "round": round_num,
                        "missing_tools": list(missing_tools),
                    })
                    # Preserve last round's text so the nag message reads
                    # naturally in the conversation history the LLM sees.
                    if round_text:
                        messages.append({"role": "assistant", "content": round_text})
                    step_list = "\n".join(f"- [{s['id']}] {s['action']} → {s['tool']}" for s in missing_steps)
                    if lang == "zh":
                        nag = f"你的 plan 还有未完成的步骤:\n{step_list}\n请立即调用对应的工具完成这些步骤。"
                    else:
                        nag = f"Your plan has unfinished steps:\n{step_list}\nPlease call the corresponding tools now."
                    messages.append({"role": "user", "content": nag})
                    continue

            # Write-claim guard: LLM's final text claims a write happened
            # (已更新/已删除/updated/deleted) but no write tool ACTUALLY executed
            # this whole run (only queries, or everything was deferred behind
            # confirm cards, or tools errored). Force one more round.
            if not write_claim_nag_used:
                has_write = bool(result.tools_executed & _WRITE_TOOLS)
                accumulated_text = "".join(text_parts)
                if not has_write and _text_claims_write(accumulated_text, lang):
                    write_claim_nag_used = True
                    trace.record("write_claim_nag_triggered", {
                        "round": round_num,
                        "tools_called": list(result.tools_called),
                        "text_sample": accumulated_text[-200:],
                    })
                    logger.warning("write_claim_nag_triggered", extra={
                        "round": round_num,
                        "tools_called": list(result.tools_called),
                    })
                    _inject_write_claim_nag(messages, round_text, lang)
                    # Clear the fabricated text from text_parts so the final
                    # response reflects the real (next-round) outcome.
                    text_parts.pop()
                    continue

            # Nudge: only fire when the LLM called zero tools. If it called
            # *some* tool (even a different one than suggested) it's clearly
            # working — don't second-guess it.
            if not nudge_used and not result.tools_called and suggested_actions:
                missed = _find_missed_tools(suggested_actions, result.tools_called)
                if missed:
                    nudge_used = True
                    trace.record("nudge_triggered", {
                        "round": round_num,
                        "missed_tools": [a.tool_name for a in missed],
                    })
                    logger.info("nudge_triggered", extra={
                        "round": round_num,
                        "missed_tools": [a.tool_name for a in missed],
                    })
                    _inject_nudge(messages, round_text, missed, lang)
                    continue

            break  # Normal exit — no tools, no pending plan, no nudge

        # Tool calls present: append assistant turn and dispatch each tool
        text_parts.append(round_text)

        assistant_msg = {
            "role": "assistant",
            "content": round_text or None,
            "tool_calls": tool_calls,
        }
        messages.append(assistant_msg)

        # If introduce_product is among the tool calls, skip all other tools
        # (LLM sometimes incorrectly records events when user is just asking about features)
        tool_names_in_round = {tc["function"]["name"] for tc in tool_calls}
        if "introduce_product" in tool_names_in_round and len(tool_calls) > 1:
            tool_calls = [tc for tc in tool_calls if tc["function"]["name"] == "introduce_product"]

        tool_results_map = {}  # tc_name → tool_result for skip_round2 check
        for tc in tool_calls:
            tc_name = tc["function"]["name"]
            tc_args_str = tc["function"]["arguments"]

            trace_log("tool_call", round=round_num, data={
                "tool_name": tc_name,
                "arguments": tc_args_str,
            })

            tool_result = await dispatch_tool(
                tc, db, user_id, session_id, result, on_card, lang,
                pets=pets, images=images, image_urls=image_urls,
                recent_image_urls=recent_image_urls,
                location=location, _messages=messages,
            )

            tool_results_map[tc_name] = tool_result

            _serialized_result = {k: v for k, v in tool_result.items() if not k.startswith("_")}
            # Size guard per spec §5.3: cap each trace entry at 64 KB.
            _payload = json.dumps(_serialized_result, ensure_ascii=False, default=str)
            if len(_payload) > 64_000:
                _serialized_result = {"_truncated": True, "_size": len(_payload), "keys": list(_serialized_result.keys())}

            trace_log("tool_result", round=round_num, data={
                "tool_name": tc_name,
                "success": tool_result.get("success"),
                "error": tool_result.get("error"),
                "result_keys": list(tool_result.keys()),
                "result": _serialized_result,     # NEW — full value with card
            })

            trace.record("tool_dispatch", {
                "round": round_num,
                "tool": tc["function"]["name"],
                "args": tc["function"]["arguments"],
                "result_keys": list(tool_result.keys()),
                "success": tool_result.get("success"),
                "error": tool_result.get("error"),
            })

            # Strip internal markers (keys starting with _) before serialising
            # back to the LLM — those are private to the orchestrator.
            serializable = {k: v for k, v in tool_result.items() if not k.startswith("_")}
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(serializable, ensure_ascii=False, default=str),
            })

            # request_images sentinel — wrap base64 payloads in an OpenAI-
            # style multimodal user message so the LLM actually sees them
            # on the next round.
            if "_inject_images" in tool_result:
                image_content = [
                    {"type": "text", "text": "这是用户附带的图片，请仔细查看后回答：" if lang == "zh" else "Here are the user's images:"}
                ]
                for img_b64 in tool_result["_inject_images"]:
                    image_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    })
                messages.append({"role": "user", "content": image_content})

        # --- Skip Round 2: if all tools are simple CRUD and succeeded,
        # use the LLM's Round 1 streaming text as the final response.
        # This saves ~8000 prompt tokens per skipped round. ---
        if _can_skip_round2(tool_calls, tool_results_map, result, round_text):
            trace.record("skip_round2", {
                "round": round_num,
                "tools": list(tool_names_in_round),
            })
            logger.info("skip_round2", extra={
                "round": round_num,
                "tools": list(tool_names_in_round),
            })
            break

    # Ensure response_text is non-empty unless the only output is a confirm
    # card (in which case the card itself is the "reply"). This guarantees
    # the user never sees a blank bubble.
    import re as _re
    raw_text = "".join(text_parts)
    # Strip leaked XML/HTML tags from LLM output (grok sometimes outputs <parameter> or <xai:function_call>)
    result.response_text = _re.sub(r"</?(?:parameter|xai:function_call|function_call)[^>]*>", "", raw_text).strip()

    # Final fabrication guard: if the LLM's response claims a write ("已删除
    # /updated") but no write tool actually executed AND no confirm card is
    # pending (the card itself would signal "pending" correctly), replace the
    # fabricated text with an honest failure message and emit a warning card.
    # This is Level 2 "UI truth" — users should never see a lie.
    has_real_write = bool(result.tools_executed & _WRITE_TOOLS)
    has_pending_confirm = bool(result.confirm_cards)
    if (
        not has_real_write
        and not has_pending_confirm
        and _text_claims_write(result.response_text, lang)
    ):
        logger.warning("fabrication_blocked", extra={
            "tools_called": list(result.tools_called),
            "tools_executed": list(result.tools_executed),
            "text_sample": result.response_text[:200],
        })
        trace.record("fabrication_blocked", {
            "tools_called": list(result.tools_called),
            "tools_executed": list(result.tools_executed),
            "text_sample": result.response_text[:200],
        })
        if lang == "zh":
            honest = (
                "抱歉，这条操作我没能成功执行 😔\n"
                "请再说一次您的请求，或者在日历/档案里手动操作。"
            )
            warn_message = "操作未能完成，数据库未变更"
        else:
            honest = (
                "Sorry — I couldn't actually execute that action 😔\n"
                "Please try saying it again, or do it manually in the calendar / profile."
            )
            warn_message = "Action did not complete — database unchanged"
        result.response_text = honest
        warning_card = {
            "type": "warning",
            "severity": "error",
            "message": warn_message,
        }
        result.cards.append(warning_card)
        if on_card:
            await maybe_await(on_card, warning_card)

    if not result.response_text.strip() and not result.confirm_cards and not result.cards:
        fallback = t("fallback_error", lang)
        result.response_text = fallback
        if on_token:
            await maybe_await(on_token, fallback)

    return result
