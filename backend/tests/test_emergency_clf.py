"""Emergency classifier sidecar client: mode resolution, timeout fallback, prompt contract."""
import asyncio

import httpx
import pytest

from app.agents import emergency_clf
from app.agents.emergency import EmergencyCheckResult, build_emergency_hint
from app.agents.emergency_clf import ClfResult, resolve

KW_HIT = EmergencyCheckResult(detected=True, keywords=["中毒"])
KW_MISS = EmergencyCheckResult(detected=False, keywords=[])
CLF_YES = ClfResult(p_true=0.97, decided=True, latency_ms=20)
CLF_NO = ClfResult(p_true=0.02, decided=False, latency_ms=20)


@pytest.mark.parametrize("mode,keyword,clf,expected", [
    # off / shadow: keyword decides, classifier ignored
    ("off", KW_MISS, CLF_YES, False),
    ("shadow", KW_MISS, CLF_YES, False),
    ("shadow", KW_HIT, CLF_NO, True),
    # union: either
    ("union", KW_MISS, CLF_YES, True),
    ("union", KW_HIT, CLF_NO, True),
    ("union", KW_MISS, CLF_NO, False),
    ("union", KW_MISS, None, False),
    # clf: classifier decides, keyword only as fallback when unavailable
    ("clf", KW_HIT, CLF_NO, False),
    ("clf", KW_MISS, CLF_YES, True),
    ("clf", KW_HIT, None, True),
    ("clf", KW_MISS, None, False),
])
def test_resolve_modes(mode, keyword, clf, expected):
    assert resolve(keyword, clf, mode).detected is expected


def test_resolve_keeps_keywords_only_when_detected():
    assert resolve(KW_HIT, CLF_YES, "union").keywords == ["中毒"]
    assert resolve(KW_MISS, CLF_YES, "union").keywords == []
    assert resolve(KW_HIT, CLF_NO, "clf").keywords == []


def test_hint_without_keywords_names_the_classifier():
    zh = build_emergency_hint([], lang="zh")
    en = build_emergency_hint([], lang="en")
    assert "紧急分类模型" in zh and "trigger_emergency" in zh
    assert "classifier" in en and "trigger_emergency" in en
    assert "中毒" in build_emergency_hint(["中毒"], lang="zh")


def test_get_mode_off_without_url(monkeypatch):
    monkeypatch.setattr(emergency_clf.settings, "emergency_clf_url", "")
    assert emergency_clf.get_mode() == "off"


def test_get_mode_defaults_to_shadow_and_rejects_garbage(monkeypatch):
    monkeypatch.setattr(emergency_clf.settings, "emergency_clf_url", "http://127.0.0.1:8081")
    from app import flags
    monkeypatch.setattr(flags, "_cache", {})
    assert emergency_clf.get_mode() == "shadow"
    monkeypatch.setattr(flags, "_cache", {"emergency_clf_mode": "CLF"})
    assert emergency_clf.get_mode() == "clf"
    monkeypatch.setattr(flags, "_cache", {"emergency_clf_mode": "banana"})
    assert emergency_clf.get_mode() == "shadow"


def test_p_true_from_llama_server_response():
    body = {"completion_probabilities": [{"token": "true", "top_logprobs": [
        {"token": "true", "logprob": -0.2}, {"token": "false", "logprob": -1.7}]}]}
    p = emergency_clf._p_true_from_response(body)
    assert 0.8 < p < 0.85
    # only one of the pair present → saturates instead of crashing
    body["completion_probabilities"][0]["top_logprobs"] = [{"token": "false", "logprob": -0.1}]
    assert emergency_clf._p_true_from_response(body) < 1e-6


def _patch_transport(monkeypatch, handler):
    real = httpx.AsyncClient

    def fake_client(**kw):
        return real(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(emergency_clf.httpx, "AsyncClient", fake_client)


@pytest.mark.asyncio
async def test_classify_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(emergency_clf.settings, "emergency_clf_url", "")
    assert await emergency_clf.classify("狗吃了老鼠药") is None


@pytest.mark.asyncio
async def test_classify_parses_server_and_applies_threshold(monkeypatch):
    monkeypatch.setattr(emergency_clf.settings, "emergency_clf_url", "http://clf")
    monkeypatch.setattr(emergency_clf.settings, "emergency_clf_threshold", 0.5)
    seen = {}

    def handler(request):
        seen["json"] = request.read().decode()
        return httpx.Response(200, json={"completion_probabilities": [{"token": "true", "top_logprobs": [
            {"token": "true", "logprob": -0.1}, {"token": "false", "logprob": -2.5}]}]})

    _patch_transport(monkeypatch, handler)
    r = await emergency_clf.classify("狗吃了老鼠药")
    assert r is not None and r.decided and r.p_true > 0.9
    # the prompt bytes come from nano.contract, thinking disabled, answer slot open
    assert "狗吃了老鼠药" in seen["json"] and "<think>" in seen["json"]


@pytest.mark.asyncio
async def test_classify_timeout_falls_back_to_none(monkeypatch):
    monkeypatch.setattr(emergency_clf.settings, "emergency_clf_url", "http://clf")

    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    _patch_transport(monkeypatch, slow)
    assert await emergency_clf.classify("狗吃了老鼠药", timeout_ms=50) is None


@pytest.mark.asyncio
async def test_classify_server_error_falls_back_to_none(monkeypatch):
    monkeypatch.setattr(emergency_clf.settings, "emergency_clf_url", "http://clf")
    _patch_transport(monkeypatch, lambda request: httpx.Response(503, text="loading"))
    assert await emergency_clf.classify("狗吃了老鼠药") is None
