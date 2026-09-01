import pytest

from app.config import settings
from app.memory.embeddings import _CACHE, embed_text


def test_embedding_model_defaults_to_openai_model_name():
    assert settings.embedding_model == "text-embedding-3-small"


def test_settings_define_embedding_endpoint_fields():
    assert hasattr(settings, "embedding_api_base")
    assert hasattr(settings, "embedding_api_key")


@pytest.mark.asyncio
async def test_embed_text_uses_embedding_endpoint_not_chat_endpoint(monkeypatch):
    _CACHE.clear()
    captured = {}

    assert hasattr(settings, "embedding_api_base")
    assert hasattr(settings, "embedding_api_key")

    monkeypatch.setattr(settings, "memory_embed_cache_size", 0)
    monkeypatch.setattr(settings, "embedding_model", "text-embedding-3-small")
    monkeypatch.setattr(settings, "model_api_base", "https://chat.example/v1")
    monkeypatch.setattr(settings, "model_api_key", "chat-key")
    monkeypatch.setattr(settings, "embedding_api_base", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "embedding_api_key", "embedding-key")

    async def fake_aembedding(**kwargs):
        captured.update(kwargs)

        class Response:
            data = [{"embedding": [0.1] * 1536}]

        return Response()

    monkeypatch.setattr("app.memory.embeddings.litellm.aembedding", fake_aembedding)

    vector = await embed_text("维尼今天吐了")

    assert len(vector) == 1536
    assert captured["model"] == "text-embedding-3-small"
    assert captured["api_base"] == "https://api.openai.com/v1"
    assert captured["api_key"] == "embedding-key"
