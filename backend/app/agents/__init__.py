from .base import BaseAgent
from .chat_agent import ChatAgent
from .emergency import detect_emergency
from .tools import TOOL_DEFINITIONS, execute_tool
from .validation import validate_tool_args

__all__ = [
    "BaseAgent",
    "ChatAgent",
    "TOOL_DEFINITIONS",
    "detect_emergency",
    "execute_tool",
    "validate_tool_args",
    "llm_extra_kwargs",
]


def llm_extra_kwargs() -> dict:
    """Return api_base and api_key kwargs for litellm calls."""
    from app.config import settings
    kw: dict = {}
    if settings.model_api_base:
        kw["api_base"] = settings.model_api_base
    if settings.model_api_key:
        kw["api_key"] = settings.model_api_key
    return kw
