"""Schema validation for tool call arguments.

Validates LLM-generated arguments before they reach the executor.
Each validator returns a list of human-readable error strings; empty
means valid. `orchestrator.dispatch_tool` feeds errors back to the LLM
as a tool_result so it can self-correct on the next round without
extra prompt engineering.

Validators are registered via `@_register(tool_name)`. Unregistered
tools pass through — validation is best-effort, not exhaustive.
Ownership checks live in the handlers (tools/*.py); this module only
does shape/type/enum checks.
"""

import re
import uuid
from datetime import date, datetime

_CATEGORIES = {"daily", "diet", "medical", "abnormal"}
_SPECIES = {"dog", "cat", "other"}
_REMINDER_TYPES = {"medication", "vaccine", "checkup", "feeding", "grooming", "other"}
_TASK_TYPES = {"routine", "special"}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _check_required(args: dict, fields: list[str]) -> list[str]:
    return [f"Missing required field: {f}" for f in fields if f not in args]


def _check_uuid(args: dict, field: str) -> list[str]:
    val = args.get(field)
    if val is None:
        return []
    try:
        uuid.UUID(str(val))
        return []
    except ValueError:
        return [f"Invalid UUID for {field}: {val!r}"]


def _check_date(args: dict, field: str) -> list[str]:
    val = args.get(field)
    if val is None:
        return []
    if not _DATE_RE.match(str(val)):
        return [f"Invalid date format for {field}: {val!r} (expected YYYY-MM-DD)"]
    try:
        date.fromisoformat(str(val))
        return []
    except ValueError:
        return [f"Invalid date for {field}: {val!r}"]


def _check_time(args: dict, field: str) -> list[str]:
    val = args.get(field)
    if val is None:
        return []
    if not _TIME_RE.match(str(val)):
        return [f"Invalid time format for {field}: {val!r} (expected HH:MM)"]
    return []


def _check_datetime(args: dict, field: str) -> list[str]:
    val = args.get(field)
    if val is None:
        return []
    try:
        datetime.fromisoformat(str(val))
        return []
    except ValueError:
        return [f"Invalid datetime for {field}: {val!r} (expected ISO 8601, e.g. 2026-03-22T10:00:00)"]


def _check_enum(args: dict, field: str, valid: set[str], label: str) -> list[str]:
    val = args.get(field)
    if val is None:
        return []
    if str(val) not in valid:
        return [f"Invalid {label} for {field}: {val!r} (must be one of: {', '.join(sorted(valid))})"]
    return []


_VALIDATORS: dict[str, callable] = {}


def _register(name: str):
    def decorator(fn):
        _VALIDATORS[name] = fn
        return fn
    return decorator


@_register("create_calendar_event")
def _validate_create_calendar_event(args: dict) -> list[str]:
    errors = _check_required(args, ["pet_id", "event_date", "title", "category"])
    errors += _check_uuid(args, "pet_id")
    errors += _check_date(args, "event_date")
    errors += _check_enum(args, "category", _CATEGORIES, "category")
    errors += _check_time(args, "event_time")
    cost = args.get("cost")
    if cost is not None and (not isinstance(cost, (int, float)) or cost < 0):
        errors.append(f"cost must be a non-negative number, got: {cost!r}")
    return errors


@_register("query_calendar_events")
def _validate_query_calendar_events(args: dict) -> list[str]:
    errors = _check_uuid(args, "pet_id")
    errors += _check_date(args, "start_date")
    errors += _check_date(args, "end_date")
    errors += _check_enum(args, "category", _CATEGORIES, "category")
    return errors


@_register("create_pet")
def _validate_create_pet(args: dict) -> list[str]:
    errors = _check_required(args, ["name", "species"])
    errors += _check_enum(args, "species", _SPECIES, "species")
    errors += _check_date(args, "birthday")
    return errors


@_register("update_pet_profile")
def _validate_update_pet_profile(args: dict) -> list[str]:
    errors = _check_required(args, ["pet_id", "info"])
    errors += _check_uuid(args, "pet_id")
    return errors


@_register("list_pets")
def _validate_list_pets(args: dict) -> list[str]:
    return []


@_register("create_reminder")
def _validate_create_reminder(args: dict) -> list[str]:
    errors = _check_required(args, ["pet_id", "type", "title", "trigger_at"])
    errors += _check_uuid(args, "pet_id")
    errors += _check_enum(args, "type", _REMINDER_TYPES, "reminder type")
    errors += _check_datetime(args, "trigger_at")
    return errors


@_register("sync_calendar")
def _validate_sync_calendar(args: dict) -> list[str]:
    return []


@_register("search_places")
def _validate_search_places(args: dict) -> list[str]:
    return _check_required(args, ["query"])


@_register("get_place_details")
def _validate_get_place_details(args: dict) -> list[str]:
    return _check_required(args, ["place_id"])


@_register("get_directions")
def _validate_get_directions(args: dict) -> list[str]:
    errors = _check_required(args, ["dest_lat", "dest_lng", "dest_name"])
    mode = args.get("mode", "driving")
    if mode not in {"driving", "walking"}:
        args["mode"] = "driving"
    return errors


@_register("draft_email")
def _validate_draft_email(args: dict) -> list[str]:
    return _check_required(args, ["subject", "body"])


@_register("introduce_product")
def _validate_introduce_product(args: dict) -> list[str]:
    return []


@_register("update_calendar_event")
def _validate_update_calendar_event(args: dict) -> list[str]:
    errors = _check_required(args, ["event_id"])
    errors += _check_uuid(args, "event_id")
    errors += _check_date(args, "event_date")
    errors += _check_time(args, "event_time")
    errors += _check_enum(args, "category", _CATEGORIES, "category")
    return errors


@_register("delete_pet")
def _validate_delete_pet(args: dict) -> list[str]:
    errors = _check_required(args, ["pet_id"])
    errors += _check_uuid(args, "pet_id")
    return errors


@_register("delete_calendar_event")
def _validate_delete_calendar_event(args: dict) -> list[str]:
    errors = _check_required(args, ["event_id"])
    errors += _check_uuid(args, "event_id")
    return errors


@_register("update_reminder")
def _validate_update_reminder(args: dict) -> list[str]:
    errors = _check_required(args, ["reminder_id"])
    errors += _check_uuid(args, "reminder_id")
    errors += _check_enum(args, "type", _REMINDER_TYPES, "reminder type")
    errors += _check_datetime(args, "trigger_at")
    return errors


@_register("delete_reminder")
def _validate_delete_reminder(args: dict) -> list[str]:
    errors = _check_required(args, ["reminder_id"])
    errors += _check_uuid(args, "reminder_id")
    return errors


@_register("delete_all_reminders")
def _validate_delete_all_reminders(args: dict) -> list[str]:
    return []  # No arguments needed


@_register("save_pet_profile_md")
def _validate_save_pet_profile_md(args: dict) -> list[str]:
    errors = _check_required(args, ["pet_id", "profile_md"])
    errors += _check_uuid(args, "pet_id")
    md = args.get("profile_md", "")
    if isinstance(md, str) and len(md) > 3000:
        errors.append(f"profile_md too long: {len(md)} chars (max 3000)")
    return errors


@_register("summarize_pet_profile")
def _validate_summarize_pet_profile(args: dict) -> list[str]:
    errors = _check_required(args, ["pet_id"])
    errors += _check_uuid(args, "pet_id")
    return errors


@_register("set_pet_avatar")
def _validate_set_pet_avatar(args: dict) -> list[str]:
    errors = _check_required(args, ["pet_id"])
    errors += _check_uuid(args, "pet_id")
    return errors


@_register("upload_event_photo")
def _validate_upload_event_photo(args: dict) -> list[str]:
    errors = _check_required(args, ["event_id"])
    errors += _check_uuid(args, "event_id")
    return errors


@_register("remove_event_photo")
def _validate_remove_event_photo(args: dict) -> list[str]:
    errors = _check_required(args, ["event_id", "photo_index"])
    errors += _check_uuid(args, "event_id")
    idx = args.get("photo_index")
    if idx is not None and (not isinstance(idx, int) or idx < 0):
        errors.append("photo_index must be a non-negative integer")
    return errors


@_register("list_reminders")
def _validate_list_reminders(args: dict) -> list[str]:
    return []


@_register("trigger_emergency")
def _validate_trigger_emergency(args: dict) -> list[str]:
    return _check_required(args, ["message"])


@_register("create_daily_task")
def _validate_create_daily_task(args: dict) -> list[str]:
    errors = _check_required(args, ["title"])
    errors += _check_uuid(args, "pet_id")
    errors += _check_date(args, "start_date")
    errors += _check_date(args, "end_date")
    target = args.get("daily_target")
    if target is not None and (not isinstance(target, int) or target < 1):
        errors.append(f"daily_target must be a positive integer, got: {target!r}")
    return errors


@_register("manage_daily_task")
def _validate_manage_daily_task(args: dict) -> list[str]:
    errors = _check_required(args, ["action"])
    errors += _check_enum(args, "action", {"update", "delete", "deactivate", "delete_all"}, "action")
    errors += _check_uuid(args, "task_id")
    # delete_all doesn't need task_id or title
    if args.get("action") != "delete_all" and not args.get("task_id") and not args.get("title"):
        errors.append("Either task_id or title is required to identify the task")
    return errors


@_register("search_knowledge")
def _validate_search_knowledge(args: dict) -> list[str]:
    errors = _check_required(args, ["query"])
    errors += _check_uuid(args, "pet_id")
    if args.get("species") and args["species"] not in _SPECIES:
        errors.append(f"Invalid species: {args['species']!r} (expected dog/cat/other)")
    return errors


def validate_tool_args(tool_name: str, arguments: dict) -> list[str]:
    """Validate tool arguments against the schema.

    Returns:
        List of error strings. Empty list means valid.
    """
    validator = _VALIDATORS.get(tool_name)
    if validator is None:
        return []
    return validator(arguments)
