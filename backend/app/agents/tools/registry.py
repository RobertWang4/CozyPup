"""Tool registration decorator + registry.

Domain files (calendar.py, pets.py, etc.) register handlers at import
time via the `@register_tool` decorator. `tools/__init__.py` then
imports every domain module to trigger the decorators, and the
orchestrator dispatches through `get_registered_tools()`.

`accepts_kwargs=True` means the handler takes extra context (image_urls,
location, lang) beyond the standard `(arguments, db, user_id)` signature.

Usage:
    from app.agents.tools.registry import register_tool

    @register_tool("create_calendar_event", accepts_kwargs=True)
    async def create_calendar_event(arguments, db, user_id, **kwargs):
        ...
"""

from typing import Any, Callable

from app.agents.tools.specs import ToolSpec

_REGISTRY: dict[str, dict] = {}
_SPECS: dict[str, ToolSpec] = {}


async def _missing_handler(*args, **kwargs) -> dict[str, Any]:
    raise ValueError("Tool is handled outside the registry")


def register_tool(
    name: str,
    *,
    accepts_kwargs: bool = False,
    description: str = "",
    input_schema: dict[str, Any] | None = None,
    read_only: bool = False,
    destructive: bool = False,
    requires_confirmation: bool = False,
    concurrency_safe: bool = False,
    search_hint: str = "",
    tags: tuple[str, ...] = (),
) -> Callable:
    """Decorator to register a tool handler."""
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[name] = {
            "handler": fn,
            "accepts_kwargs": accepts_kwargs,
        }
        if description or input_schema is not None:
            _SPECS[name] = ToolSpec(
                name=name,
                description=description,
                input_schema=input_schema or {"type": "object", "properties": {}},
                handler=fn,
                accepts_kwargs=accepts_kwargs,
                read_only=read_only,
                destructive=destructive,
                requires_confirmation=requires_confirmation,
                concurrency_safe=concurrency_safe,
                search_hint=search_hint,
                tags=tags,
            )
        return fn
    return decorator


def get_registered_tools() -> dict[str, dict]:
    """Return the full registry. Call after all domain modules are imported."""
    return _REGISTRY


def _validator_for(name: str):
    from app.agents.validation import validate_tool_args

    def validator(arguments: dict[str, Any]) -> str | None:
        errors = validate_tool_args(name, arguments)
        if not errors:
            return None
        return "; ".join(errors)

    return validator


def _is_read_only(name: str) -> bool:
    return name.startswith(("query_", "list_", "search_", "get_")) or name in {
        "introduce_product",
        "plan",
        "request_images",
        "sync_calendar",
    }


def _is_destructive(name: str) -> bool:
    if name.startswith(("delete_", "remove_")):
        return True
    from app.agents.constants import CONDITIONAL_CONFIRM_ACTIONS

    return bool(CONDITIONAL_CONFIRM_ACTIONS.get(name))


def _requires_confirmation(name: str) -> bool:
    from app.agents.constants import (
        CONDITIONAL_CONFIRM_ACTIONS,
        CONFIRM_TOOLS,
        MUTATING_TOOLS_WITH_VERB_BYPASS,
    )

    return (
        name in CONFIRM_TOOLS
        or name in MUTATING_TOOLS_WITH_VERB_BYPASS
        or name in CONDITIONAL_CONFIRM_ACTIONS
    )


def _spec_from_definition(definition: dict[str, Any]) -> ToolSpec:
    fn = definition["function"]
    name = fn["name"]
    registered = _REGISTRY.get(name, {})
    existing = _SPECS.get(name)
    handler = registered.get("handler") or (existing.handler if existing else _missing_handler)
    accepts_kwargs = registered.get("accepts_kwargs", existing.accepts_kwargs if existing else False)

    return ToolSpec(
        name=name,
        description=existing.description if existing and existing.description else fn.get("description", ""),
        input_schema=existing.input_schema if existing and existing.input_schema else fn.get("parameters", {}),
        handler=handler,
        validate=existing.validate if existing and existing.validate else _validator_for(name),
        accepts_kwargs=accepts_kwargs,
        read_only=(existing.read_only if existing else False) or _is_read_only(name),
        destructive=(existing.destructive if existing else False) or _is_destructive(name),
        requires_confirmation=(existing.requires_confirmation if existing else False) or _requires_confirmation(name),
        concurrency_safe=existing.concurrency_safe if existing else False,
        search_hint=existing.search_hint if existing else "",
        tags=existing.tags if existing else (),
    )


def get_tool_specs() -> dict[str, ToolSpec]:
    """Return canonical tool specs hydrated from existing metadata."""
    from app.agents.tools.definitions import get_tool_definitions

    specs = dict(_SPECS)
    for definition in get_tool_definitions():
        specs[definition["function"]["name"]] = _spec_from_definition(definition)

    for name, entry in _REGISTRY.items():
        if name not in specs:
            specs[name] = ToolSpec(
                name=name,
                description="",
                input_schema={"type": "object", "properties": {}},
                handler=entry["handler"],
                accepts_kwargs=entry["accepts_kwargs"],
            )
    return specs
