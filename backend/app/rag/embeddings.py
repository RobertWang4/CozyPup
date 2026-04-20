"""Generate embeddings via LiteLLM (OpenAI text-embedding-3-small).

Bounded in-process LRU keeps repeat queries (and ingest reruns of identical
chunks) from hitting the embedding API. Cache is per-process — horizontal
scaling still redoes work across replicas, but that's fine at current volume.
"""

import logging
from collections import OrderedDict

import litellm

from app.config import settings

logger = logging.getLogger(__name__)

_CACHE: "OrderedDict[tuple[str, str], list[float]]" = OrderedDict()


async def embed_text(text: str) -> list[float]:
    """Generate a 1536-dim embedding for a single text string."""
    cache_size = settings.rag_embed_cache_size
    key = (settings.embedding_model, text)

    if cache_size > 0 and key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]

    from app.agents import llm_extra_kwargs  # lazy import to avoid circular deps
    response = await litellm.aembedding(
        model=settings.embedding_model,
        input=[text],
        **llm_extra_kwargs(),
    )
    vector = response.data[0].embedding

    if cache_size > 0:
        _CACHE[key] = vector
        while len(_CACHE) > cache_size:
            _CACHE.popitem(last=False)

    return vector
