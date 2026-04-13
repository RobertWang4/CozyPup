"""Tests for ChatRateLimit module-level clear() helper."""
import pytest

from app.middleware import rate_limit


def setup_function(_):
    rate_limit._buckets.clear()


def test_clear_one_user_removes_only_their_bucket():
    rate_limit._buckets["alice"].timestamps.append(1.0)
    rate_limit._buckets["bob"].timestamps.append(2.0)
    rate_limit.clear("alice")
    assert "alice" not in rate_limit._buckets
    assert "bob" in rate_limit._buckets


def test_clear_all_wipes_everything():
    rate_limit._buckets["alice"].timestamps.append(1.0)
    rate_limit._buckets["bob"].timestamps.append(2.0)
    rate_limit.clear(None)
    assert len(rate_limit._buckets) == 0


def test_max_per_hour_reads_flag(monkeypatch):
    from app import flags
    flags._cache.clear()
    flags._set_in_cache("chat_rate_limit_per_hour", 5)
    assert rate_limit.current_limit_per_hour() == 5
    flags._cache.clear()
    assert rate_limit.current_limit_per_hour() == rate_limit.MAX_MESSAGES_PER_HOUR
