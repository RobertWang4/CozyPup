"""Global daily cap on POST /chat (cost guard while the app is free)."""

from app import flags as _flags
from app.middleware import rate_limit


def setup_function(_):
    rate_limit.reset_daily_counter()
    _flags._cache.pop("daily_chat_cap", None)


def teardown_function(_):
    rate_limit.reset_daily_counter()
    _flags._cache.pop("daily_chat_cap", None)


def test_daily_cap_blocks_after_limit():
    _flags._set_in_cache("daily_chat_cap", 2)
    assert rate_limit._daily_cap_reached() is False
    assert rate_limit._daily_cap_reached() is False
    assert rate_limit._daily_cap_reached() is True
    assert rate_limit._daily_cap_reached() is True


def test_daily_cap_zero_disables_cap():
    _flags._set_in_cache("daily_chat_cap", 0)
    for _ in range(5):
        assert rate_limit._daily_cap_reached() is False


def test_daily_cap_defaults_to_constant():
    assert rate_limit.DAILY_CHAT_CAP > 0
    for _ in range(3):
        assert rate_limit._daily_cap_reached() is False
    assert rate_limit._daily["count"] == 3
