"""Agents package — unified ChatAgent, tool definitions, and LLM helpers.

Re-exports the main entry points used by the chat router:
- TOOL_DEFINITIONS: OpenAI-style function schemas exposed to the LLM
- execute_tool: dispatch entry for tool handlers
- validate_tool_args: schema/ownership validation
- detect_emergency: keyword detector that routes to the emergency model
- llm_extra_kwargs: injects MODEL_API_BASE / MODEL_API_KEY into litellm calls
"""

from .emergency import detect_emergency
from .tools import TOOL_DEFINITIONS, execute_tool
from .validation import validate_tool_args

__all__ = [
    "TOOL_DEFINITIONS",
    "detect_emergency",
    "execute_tool",
    "validate_tool_args",
    "llm_extra_kwargs",
]


def llm_extra_kwargs() -> dict:
    """Return api_base and api_key kwargs for every litellm call.

    Centralised so we can point at the LiteLLM proxy (DeepSeek/Grok/Kimi) via
    a single settings module without every call site knowing about it.
    """
    from app.config import settings
    kw: dict = {}
    if settings.model_api_base:
        kw["api_base"] = settings.model_api_base
    if settings.model_api_key:
        kw["api_key"] = settings.model_api_key
    return kw
