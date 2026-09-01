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
    "AgentEngine",
    "AgentRunInput",
    "TOOL_DEFINITIONS",
    "detect_emergency",
    "execute_tool",
    "validate_tool_args",
    "llm_extra_kwargs",
]


def llm_extra_kwargs(vision: bool = False) -> dict:
    """Return api_base and api_key kwargs for every litellm call.

    Centralised so we can point at the LiteLLM proxy (DeepSeek/Grok/Kimi) via
    a single settings module without every call site knowing about it.

    When vision=True and vision_model_api_base/key are set, those override
    the main model_api_base/key (used to route Grok through a proxy while
    chat stays on DeepSeek official API).
    """
    from app.config import settings
    kw: dict = {}
    api_base = settings.model_api_base
    api_key = settings.model_api_key
    if vision:
        if settings.vision_model_api_base:
            api_base = settings.vision_model_api_base
        if settings.vision_model_api_key:
            api_key = settings.vision_model_api_key
    if api_base:
        kw["api_base"] = api_base
    if api_key:
        kw["api_key"] = api_key
    return kw


def __getattr__(name: str):
    if name in {"AgentEngine", "AgentRunInput"}:
        from .engine import AgentEngine, AgentRunInput

        return {"AgentEngine": AgentEngine, "AgentRunInput": AgentRunInput}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
