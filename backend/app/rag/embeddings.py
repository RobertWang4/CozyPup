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
    item = response.data[0]
    vector = item["embedding"] if isinstance(item, dict) else item.embedding

    if cache_size > 0:
        _CACHE[key] = vector
        while len(_CACHE) > cache_size:
            _CACHE.popitem(last=False)

    return vector


# OpenAI's embedding endpoint accepts up to 2048 inputs per request. Keep some
# headroom so we don't brush the cap on long titles.
_EMBED_BATCH_CAP = 1024


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings in as few API calls as possible.

    Returns vectors in the same order as the input. Cached items are served
    without touching the API; only cache misses are sent (deduped) in chunks
    of up to _EMBED_BATCH_CAP. Use this over a loop of embed_text when
    ingesting lots of chunks at once.
    """
    cache_size = settings.rag_embed_cache_size
    model = settings.embedding_model
    results: list[list[float] | None] = [None] * len(texts)

    # Serve from cache first, then collect the unique cache-miss texts.
    misses: dict[str, list[int]] = {}
    for i, text in enumerate(texts):
        key = (model, text)
        if cache_size > 0 and key in _CACHE:
            _CACHE.move_to_end(key)
            results[i] = _CACHE[key]
        else:
            misses.setdefault(text, []).append(i)

    if misses:
        from app.agents import llm_extra_kwargs  # lazy import to avoid circular deps
        unique_texts = list(misses.keys())
        for start in range(0, len(unique_texts), _EMBED_BATCH_CAP):
            batch = unique_texts[start : start + _EMBED_BATCH_CAP]
            response = await litellm.aembedding(
                model=model,
                input=batch,
                **llm_extra_kwargs(),
            )
            for text, item in zip(batch, response.data):
                vector = item["embedding"] if isinstance(item, dict) else item.embedding
                for idx in misses[text]:
                    results[idx] = vector
                if cache_size > 0:
                    _CACHE[(model, text)] = vector

        if cache_size > 0:
            while len(_CACHE) > cache_size:
                _CACHE.popitem(last=False)

    return [v for v in results if v is not None]
