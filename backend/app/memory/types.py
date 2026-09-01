from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MemorySnippet:
    kind: str
    content: str
    date: str | None = None
    entity_id: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeSnippet:
    title: str
    content: str
    url: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievedContext:
    behavioral_memories: list[MemorySnippet] = field(default_factory=list)
    cognitive_memories: list[MemorySnippet] = field(default_factory=list)
    knowledge_snippets: list[KnowledgeSnippet] = field(default_factory=list)

    @property
    def personal_memories(self) -> list[MemorySnippet]:
        return [*self.behavioral_memories, *self.cognitive_memories]

    def has_content(self) -> bool:
        return bool(
            self.behavioral_memories
            or self.cognitive_memories
            or self.knowledge_snippets
        )
