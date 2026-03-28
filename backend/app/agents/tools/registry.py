"""Tool registration decorator and registry.

Usage in domain files:
    from app.agents.tools.registry import register_tool

    @register_tool("create_calendar_event", accepts_kwargs=True)
    async def create_calendar_event(arguments, db, user_id, **kwargs):
        ...
"""

from typing import Callable

_REGISTRY: dict[str, dict] = {}


def register_tool(
    name: str,
    *,
    accepts_kwargs: bool = False,
) -> Callable:
    """Decorator to register a tool handler."""
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[name] = {
            "handler": fn,
            "accepts_kwargs": accepts_kwargs,
        }
        return fn
    return decorator


def get_registered_tools() -> dict[str, dict]:
    """Return the full registry. Call after all domain modules are imported."""
    return _REGISTRY
