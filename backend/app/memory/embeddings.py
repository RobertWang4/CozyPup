"""Embedding helpers for MemWeaver memory nodes."""

from __future__ import annotations

from collections import OrderedDict

import litellm

from app.config import settings

_CACHE: "OrderedDict[tuple[str, str], list[float]]" = OrderedDict()


def _embedding_extra_kwargs() -> dict:
    kwargs: dict = {}
    if settings.embedding_api_base:
        kwargs["api_base"] = settings.embedding_api_base
    if settings.embedding_api_key:
        kwargs["api_key"] = settings.embedding_api_key
    return kwargs


async def embed_text(text: str) -> list[float]:
    cache_size = settings.memory_embed_cache_size
    key = (settings.embedding_model, text)

    if cache_size > 0 and key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]

    response = await litellm.aembedding(
        model=settings.embedding_model,
        input=[text],
        **_embedding_extra_kwargs(),
    )
    item = response.data[0]
    vector = item["embedding"] if isinstance(item, dict) else item.embedding

    if cache_size > 0:
        _CACHE[key] = vector
        while len(_CACHE) > cache_size:
            _CACHE.popitem(last=False)

    return vector
