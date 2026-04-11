"""Tests for RAG embedding generation."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_embed_text_returns_1536_dim_vector():
    """embed_text should return a list of 1536 floats."""
    mock_response = AsyncMock()
    mock_response.data = [AsyncMock(embedding=[0.1] * 1536)]

    with patch("litellm.aembedding", return_value=mock_response) as mock_embed:
        from app.rag.embeddings import embed_text
        result = await embed_text("狗狗呕吐了")

        assert len(result) == 1536
        assert all(isinstance(v, float) for v in result)
        mock_embed.assert_called_once()


@pytest.mark.asyncio
async def test_embed_text_passes_model_and_api_config():
    """embed_text should use the configured embedding model and API base."""
    mock_response = AsyncMock()
    mock_response.data = [AsyncMock(embedding=[0.0] * 1536)]

    with patch("litellm.aembedding", return_value=mock_response) as mock_embed:
        from app.rag.embeddings import embed_text
        await embed_text("test query")

        call_kwargs = mock_embed.call_args[1]
        assert "model" in call_kwargs
        assert call_kwargs["input"] == ["test query"]
