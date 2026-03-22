"""Base interfaces for RAG retrievers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class RetrievalResult:
    content: str
    source_type: str       # 'chat_turn', 'daily_summary', 'calendar_event'
    source_id: str
    score: float           # cosine similarity (0-1)
    metadata: dict = field(default_factory=dict)


class BaseRetriever(ABC):
    @abstractmethod
    async def retrieve(
        self,
        query_embedding: list[float],
        user_id: UUID,
        top_k: int = 10,
        pet_id: UUID | None = None,
    ) -> list[RetrievalResult]:
        ...
