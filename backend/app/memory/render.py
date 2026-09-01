from __future__ import annotations

from app.memory.types import KnowledgeSnippet, MemorySnippet, RetrievedContext


def _memory_line(item: MemorySnippet) -> str:
    prefix = f"[{item.date}] " if item.date else ""
    return f"- {prefix}{item.content}"


def _knowledge_line(item: KnowledgeSnippet) -> str:
    title = f"{item.title}: " if item.title else ""
    suffix = f" ({item.url})" if item.url else ""
    return f"- {title}{item.content}{suffix}"


def render_retrieved_context(
    context: RetrievedContext,
    *,
    lang: str = "zh",
    limit: int = 3,
) -> str:
    if not context.has_content():
        return ""

    parts: list[str] = []
    if context.behavioral_memories:
        parts.append("## Relevant Pet/User Memory")
        parts.extend(_memory_line(item) for item in context.behavioral_memories[:limit])

    if context.cognitive_memories:
        parts.append("## Long-Term Pet/User Memory")
        parts.extend(_memory_line(item) for item in context.cognitive_memories[:limit])

    if context.knowledge_snippets:
        parts.append("## Trusted Pet Health Knowledge")
        parts.extend(_knowledge_line(item) for item in context.knowledge_snippets[:limit])

    return "\n".join(parts)
