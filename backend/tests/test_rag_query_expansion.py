"""Tests for LLM-based query expansion."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _fake_completion(content: str):
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    return resp


@pytest.mark.asyncio
async def test_expand_query_returns_original_plus_variants():
    from app.rag import query_expansion as mod
    mod._CACHE.clear()

    call = AsyncMock(return_value=_fake_completion('["dog diarrhea", "狗腹泻"]'))
    with patch("app.rag.query_expansion.litellm.acompletion", call):
        out = await mod.expand_query("狗拉肚子")

    assert out[0] == "狗拉肚子"           # original always first
    assert "dog diarrhea" in out
    assert "狗腹泻" in out
    call.assert_awaited_once()


@pytest.mark.asyncio
async def test_expand_query_strips_code_fences():
    from app.rag import query_expansion as mod
    mod._CACHE.clear()

    wrapped = '```json\n["variant one"]\n```'
    call = AsyncMock(return_value=_fake_completion(wrapped))
    with patch("app.rag.query_expansion.litellm.acompletion", call):
        out = await mod.expand_query("q")

    assert "variant one" in out


@pytest.mark.asyncio
async def test_expand_query_falls_back_on_llm_failure():
    from app.rag import query_expansion as mod
    mod._CACHE.clear()

    call = AsyncMock(side_effect=Exception("provider down"))
    with patch("app.rag.query_expansion.litellm.acompletion", call):
        out = await mod.expand_query("狗呕吐")

    assert out == ["狗呕吐"]


@pytest.mark.asyncio
async def test_expand_query_falls_back_on_bad_json():
    from app.rag import query_expansion as mod
    mod._CACHE.clear()

    call = AsyncMock(return_value=_fake_completion("sorry, I cannot help"))
    with patch("app.rag.query_expansion.litellm.acompletion", call):
        out = await mod.expand_query("q")

    assert out == ["q"]


@pytest.mark.asyncio
async def test_expand_query_caches_repeat_calls():
    from app.rag import query_expansion as mod
    mod._CACHE.clear()

    call = AsyncMock(return_value=_fake_completion('["cached variant"]'))
    with patch("app.rag.query_expansion.litellm.acompletion", call):
        out1 = await mod.expand_query("q")
        out2 = await mod.expand_query("q")

    assert out1 == out2
    call.assert_awaited_once()


@pytest.mark.asyncio
async def test_expand_query_respects_variant_cap(monkeypatch):
    from app.rag import query_expansion as mod
    mod._CACHE.clear()
    monkeypatch.setattr(mod.settings, "rag_query_expansion_variants", 1)

    call = AsyncMock(return_value=_fake_completion('["v1", "v2", "v3"]'))
    with patch("app.rag.query_expansion.litellm.acompletion", call):
        out = await mod.expand_query("q")

    # Original + at most 1 variant.
    assert len(out) == 2
    assert out[0] == "q"


@pytest.mark.asyncio
async def test_expand_query_disabled_by_flag(monkeypatch):
    from app.rag import query_expansion as mod
    mod._CACHE.clear()
    monkeypatch.setattr(mod.settings, "rag_enable_query_expansion", False)

    call = AsyncMock()
    with patch("app.rag.query_expansion.litellm.acompletion", call):
        out = await mod.expand_query("q")

    assert out == ["q"]
    call.assert_not_called()
