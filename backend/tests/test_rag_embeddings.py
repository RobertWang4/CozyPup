"""Tests for RAG embedding generation + batching cache."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _fake_response(vectors):
    resp = MagicMock()
    resp.data = [MagicMock(embedding=v) for v in vectors]
    return resp


@pytest.mark.asyncio
async def test_embed_text_returns_1536_dim_vector():
    """embed_text should return a list of 1536 floats."""
    mock_response = _fake_response([[0.1] * 1536])

    with patch("litellm.aembedding", return_value=mock_response) as mock_embed:
        from app.rag import embeddings as mod
        mod._CACHE.clear()
        result = await mod.embed_text("狗狗呕吐了")

        assert len(result) == 1536
        assert all(isinstance(v, float) for v in result)
        mock_embed.assert_called_once()


@pytest.mark.asyncio
async def test_embed_text_passes_model_and_api_config():
    """embed_text should use the configured embedding model and API base."""
    mock_response = _fake_response([[0.0] * 1536])

    with patch("litellm.aembedding", return_value=mock_response) as mock_embed:
        from app.rag import embeddings as mod
        mod._CACHE.clear()
        await mod.embed_text("test query")

        call_kwargs = mock_embed.call_args[1]
        assert "model" in call_kwargs
        assert call_kwargs["input"] == ["test query"]


@pytest.mark.asyncio
async def test_embed_text_caches_repeat_query():
    """Second call with the same text hits the cache, not the API."""
    from app.rag import embeddings as mod
    mod._CACHE.clear()

    call = AsyncMock(return_value=_fake_response([[0.1] * 1536]))
    with patch("app.rag.embeddings.litellm.aembedding", call):
        v1 = await mod.embed_text("abc")
        v2 = await mod.embed_text("abc")

    assert v1 == v2
    call.assert_awaited_once()


@pytest.mark.asyncio
async def test_embed_texts_batches_misses_and_preserves_order():
    """embed_texts dedups inputs, batches misses, and returns vectors in input order."""
    from app.rag import embeddings as mod
    mod._CACHE.clear()

    async def fake(model, input, **kwargs):
        # Distinguishable vector per unique input.
        return _fake_response([[float(len(t))] + [0.0] * 1535 for t in input])

    with patch("app.rag.embeddings.litellm.aembedding", side_effect=fake) as call:
        vectors = await mod.embed_texts(["a", "bb", "a", "ccc"])

    assert len(vectors) == 4
    assert vectors[0] == vectors[2]       # duplicate input → same vector
    assert vectors[0][0] == 1.0
    assert vectors[1][0] == 2.0
    assert vectors[3][0] == 3.0

    call.assert_awaited_once()
    sent_batch = call.await_args.kwargs["input"]
    assert sorted(sent_batch) == ["a", "bb", "ccc"]


@pytest.mark.asyncio
async def test_embed_texts_uses_cache_before_calling_api():
    """Cache-hit entries never reach the API; only misses are sent."""
    from app.rag import embeddings as mod
    mod._CACHE.clear()
    mod._CACHE[(mod.settings.embedding_model, "warm")] = [0.5] * 1536

    async def fake(model, input, **kwargs):
        return _fake_response([[0.9] * 1536 for _ in input])

    with patch("app.rag.embeddings.litellm.aembedding", side_effect=fake) as call:
        vectors = await mod.embed_texts(["warm", "cold"])

    assert vectors[0][0] == 0.5
    assert vectors[1][0] == 0.9
    sent = call.await_args.kwargs["input"]
    assert sent == ["cold"]
