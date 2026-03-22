"""Embedding service — generates vector embeddings via LiteLLM proxy."""

import asyncio
import logging

import litellm

from app.config import settings

logger = logging.getLogger(__name__)

# Singleton
_service: "EmbeddingService | None" = None


def get_embedding_service() -> "EmbeddingService":
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service


class EmbeddingService:
    def __init__(self):
        self.model = settings.embedding_model
        self.api_base = settings.embedding_api_base or settings.model_api_base
        self.api_key = settings.embedding_api_key or settings.model_api_key
        self.timeout = 3.0

    async def embed(self, text: str) -> list[float] | None:
        """Generate embedding vector for text. Returns None on failure."""
        try:
            kwargs = dict(model=self.model, input=[text])
            if self.api_base:
                kwargs["api_base"] = self.api_base
            if self.api_key:
                kwargs["api_key"] = self.api_key

            response = await asyncio.wait_for(
                litellm.aembedding(**kwargs),
                timeout=self.timeout,
            )
            return response.data[0].embedding
        except Exception as exc:
            logger.warning("embedding_error", extra={"error": str(exc)[:200]})
            return None
