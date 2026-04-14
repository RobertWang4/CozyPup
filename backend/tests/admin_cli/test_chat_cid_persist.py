"""Unit test that chat_request trace payload contains the new fields."""
from unittest.mock import MagicMock, patch

from app.debug.correlation import set_correlation_id


def test_chat_request_trace_includes_new_fields(monkeypatch):
    """Simulate the exact line that emits chat_request and assert new keys."""
    set_correlation_id("cid-fake")
    captured = {}

    def _capture(log_type, **kwargs):
        captured[log_type] = kwargs

    with patch("app.debug.trace_logger.trace_log", side_effect=_capture):
        from app.debug.trace_logger import trace_log
        trace_log("chat_request", data={
            "message": "hello",
            "image_urls": ["u1", "u2"],
            "image_urls_full": ["https://full1", "https://full2"],
            "session_id": "s1",
            "pet_snapshot": [{"id": "p1", "name": "dou", "species": "dog", "breed": "柴犬", "age_months": 36, "weight_kg": 8.0, "chronic_conditions": []}],
            "session_history_tail": [{"role": "user", "content_preview": "prior"}],
            "client_version": "ios-1.2.3",
        })
    assert captured["chat_request"]["data"]["pet_snapshot"][0]["name"] == "dou"
    assert captured["chat_request"]["data"]["image_urls_full"] == ["https://full1", "https://full2"]
    assert "client_version" in captured["chat_request"]["data"]
