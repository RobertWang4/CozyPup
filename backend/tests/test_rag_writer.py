"""Tests for RAG embedding writer."""

import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_write_chat_embedding_stores_to_db():
    """write_chat_embedding should generate embedding and store in DB."""
    mock_embed = AsyncMock(return_value=[0.1] * 1536)
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    with patch("app.rag.embeddings.embed_text", mock_embed):
        from app.rag.writer import write_chat_embedding
        await write_chat_embedding(
            db=mock_db,
            user_id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            content="维尼今天呕吐了两次",
            pet_id=uuid.uuid4(),
        )

    mock_embed.assert_called_once_with("维尼今天呕吐了两次")
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()

    added_obj = mock_db.add.call_args[0][0]
    assert added_obj.content == "维尼今天呕吐了两次"
    assert added_obj.embedding == [0.1] * 1536


@pytest.mark.asyncio
async def test_write_chat_embedding_handles_error_gracefully():
    """write_chat_embedding should log error and not raise on failure."""
    mock_embed = AsyncMock(side_effect=Exception("API error"))
    mock_db = AsyncMock()

    with patch("app.rag.embeddings.embed_text", mock_embed):
        from app.rag.writer import write_chat_embedding
        await write_chat_embedding(
            db=mock_db,
            user_id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            content="test",
        )

    mock_db.add.assert_not_called()
