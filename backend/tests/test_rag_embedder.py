import pytest
from unittest.mock import AsyncMock, patch

from app.rag.embedder import EmbeddingService


class TestEmbeddingService:
    @pytest.mark.asyncio
    async def test_embed_returns_vector(self):
        mock_response = AsyncMock()
        mock_response.data = [AsyncMock(embedding=[0.1] * 1536)]

        with patch("app.rag.embedder.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(return_value=mock_response)
            service = EmbeddingService()
            result = await service.embed("test text")

        assert len(result) == 1536
        assert result[0] == 0.1

    @pytest.mark.asyncio
    async def test_embed_returns_none_on_timeout(self):
        with patch("app.rag.embedder.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(side_effect=TimeoutError)
            service = EmbeddingService()
            result = await service.embed("test text")

        assert result is None

    @pytest.mark.asyncio
    async def test_embed_returns_none_on_error(self):
        with patch("app.rag.embedder.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(side_effect=Exception("API error"))
            service = EmbeddingService()
            result = await service.embed("test text")

        assert result is None
