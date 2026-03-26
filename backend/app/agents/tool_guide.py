"""Decision tree for tool selection — injected into the system prompt."""

from app.agents.locale import t


def get_tool_decision_tree(lang: str = "zh") -> str:
    return t("tool_decision_tree", lang)


# Backward compat
TOOL_DECISION_TREE = get_tool_decision_tree("zh")
