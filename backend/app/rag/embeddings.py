"""Generate embeddings via LiteLLM (OpenAI text-embedding-3-small)."""

import logging

import litellm

from app.agents import llm_extra_kwargs
from app.config import settings

logger = logging.getLogger(__name__)


async def embed_text(text: str) -> list[float]:
    """Generate a 1536-dim embedding for a single text string."""
    response = await litellm.aembedding(
        model=settings.embedding_model,
        input=[text],
        **llm_extra_kwargs(),
    )
    return response.data[0].embedding
