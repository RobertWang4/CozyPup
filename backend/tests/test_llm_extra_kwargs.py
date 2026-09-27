from app.agents import llm_extra_kwargs
from app.config import settings


def test_emergency_model_uses_its_own_base(monkeypatch):
    monkeypatch.setattr(settings, "model_api_base", "https://chat.example")
    monkeypatch.setattr(settings, "model_api_key", "chat-key")
    monkeypatch.setattr(settings, "emergency_model", "openai/gpt-x")
    monkeypatch.setattr(settings, "emergency_model_api_base", "https://proxy.example/v1")
    monkeypatch.setattr(settings, "emergency_model_api_key", "proxy-key")

    assert llm_extra_kwargs(model="openai/gpt-x") == {
        "api_base": "https://proxy.example/v1", "api_key": "proxy-key",
    }
    assert llm_extra_kwargs(model="deepseek/other") == {
        "api_base": "https://chat.example", "api_key": "chat-key",
    }


def test_emergency_base_falls_back_when_unset(monkeypatch):
    monkeypatch.setattr(settings, "model_api_base", "https://chat.example")
    monkeypatch.setattr(settings, "model_api_key", "chat-key")
    monkeypatch.setattr(settings, "emergency_model", "openai/gpt-x")
    monkeypatch.setattr(settings, "emergency_model_api_base", "")
    monkeypatch.setattr(settings, "emergency_model_api_key", "")
    assert llm_extra_kwargs(model="openai/gpt-x") == {
        "api_base": "https://chat.example", "api_key": "chat-key",
    }


def test_vision_wins_over_emergency(monkeypatch):
    monkeypatch.setattr(settings, "model_api_base", "https://chat.example")
    monkeypatch.setattr(settings, "model_api_key", "chat-key")
    monkeypatch.setattr(settings, "vision_model_api_base", "https://vision.example/v1")
    monkeypatch.setattr(settings, "vision_model_api_key", "vision-key")
    monkeypatch.setattr(settings, "emergency_model", "openai/gpt-x")
    monkeypatch.setattr(settings, "emergency_model_api_base", "https://proxy.example/v1")
    assert llm_extra_kwargs(vision=True, model="openai/gpt-x")["api_base"] == "https://vision.example/v1"


def test_opencode_base_adds_identity_headers(monkeypatch):
    from app.config import settings
    from app.debug.correlation import session_id_var

    monkeypatch.setattr(settings, "model_api_base", "https://opencode.ai/zen/go/v1")
    monkeypatch.setattr(settings, "model_api_key", "k")
    token = session_id_var.set("sess-123")
    try:
        kw = llm_extra_kwargs(model="openai/deepseek-flash")
    finally:
        session_id_var.reset(token)
    assert kw["extra_headers"] == {"User-Agent": "CozyPup/1.0", "x-opencode-session": "sess-123"}


def test_non_opencode_base_has_no_extra_headers(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "model_api_base", "https://api.deepseek.com")
    assert "extra_headers" not in llm_extra_kwargs(model="openai/deepseek-flash")
