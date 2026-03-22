"""Schema validation for tool call arguments.

Validates LLM-generated arguments before they reach the executor.
Returns a list of human-readable error strings (empty = valid).
Errors are fed back to the LLM so it can retry.
"""

import re
import uuid
from datetime import date, datetime

_CATEGORIES = {"diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"}
_SPECIES = {"dog", "cat", "other"}
_REMINDER_TYPES = {"medication", "vaccine", "checkup", "feeding", "grooming", "other"}

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


def validate_tool_args(tool_name: str, arguments: dict) -> list[str]:
    """Validate tool arguments against the schema.

    Returns:
        List of error strings. Empty list means valid.
    """
    validator = _VALIDATORS.get(tool_name)
    if validator is None:
        return []
    return validator(arguments)
