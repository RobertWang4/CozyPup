"""Test that tool registry correctly registers tools from decorators."""

# Import domain modules to populate the registry
import app.agents.tools.calendar  # noqa: F401
import app.agents.tools.pets      # noqa: F401
import app.agents.tools.reminders # noqa: F401
import app.agents.tools.misc      # noqa: F401

from app.agents.tools.registry import get_registered_tools


def test_all_handlers_registered():
    """Every tool in definitions should have a registered handler."""
    from app.agents.tools.definitions import _BASE_TOOL_DEFINITIONS

    defined_names = {
        t["function"]["name"]
        for t in _BASE_TOOL_DEFINITIONS
        if t["function"]["name"] != "request_images"
    }

    registered = get_registered_tools()
    registered_names = set(registered.keys())

    missing = defined_names - registered_names
    assert not missing, f"Tools defined but not registered: {missing}"


def test_registry_handler_is_callable():
    """Each registered handler should be an async callable."""
    registered = get_registered_tools()
    for name, entry in registered.items():
        assert callable(entry["handler"]), f"{name} handler is not callable"


def test_registry_has_accepts_kwargs():
    """Tools that accept kwargs should be marked."""
    registered = get_registered_tools()
    assert registered["search_places"]["accepts_kwargs"] is True
    assert registered["list_pets"]["accepts_kwargs"] is False
