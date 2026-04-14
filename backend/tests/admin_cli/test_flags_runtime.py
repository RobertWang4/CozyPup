"""Tests for the process-local feature flag cache."""
import pytest

from app import flags


def setup_function(_):
    flags._cache.clear()
    flags._cache_loaded_at = 0.0


def test_get_flag_returns_default_when_missing():
    assert flags.get_flag("nonexistent", default=True) is True
    assert flags.get_flag("also_missing", default=42) == 42


def test_set_then_get_from_local_cache():
    flags._set_in_cache("demo_flag", True)
    assert flags.get_flag("demo_flag", default=False) is True


def test_typed_helpers():
    flags._set_in_cache("bool_flag", True)
    flags._set_in_cache("int_flag", 99)
    flags._set_in_cache("obj_flag", {"text": "hi", "severity": "info"})
    assert flags.get_bool_flag("bool_flag", default=False) is True
    assert flags.get_int_flag("int_flag", default=0) == 99
    assert flags.get_flag("obj_flag", default={}) == {"text": "hi", "severity": "info"}


def test_clear_cache():
    flags._set_in_cache("demo", "x")
    assert flags.get_flag("demo", default=None) == "x"
    flags._cache.clear()
    assert flags.get_flag("demo", default="gone") == "gone"
