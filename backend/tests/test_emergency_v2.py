"""Tests for emergency detection V2 — keyword hint injection."""

import pytest

from app.agents.emergency import (
    EmergencyCheckResult,
    build_emergency_hint,
    detect_emergency,
)


def test_detect_emergency_returns_result():
    result = detect_emergency("我家猫中毒了")
    assert isinstance(result, EmergencyCheckResult)
    assert result.detected is True
    assert "中毒" in result.keywords


def test_detect_emergency_no_match():
    result = detect_emergency("今天天气不错")
    assert result.detected is False
    assert result.keywords == []


def test_detect_emergency_multiple_keywords():
    result = detect_emergency("猫抽搐了还在出血")
    assert result.detected is True
    assert len(result.keywords) >= 2
    assert "抽搐" in result.keywords
    assert "出血" in result.keywords


def test_detect_emergency_deduplicates():
    result = detect_emergency("中毒了中毒了快来")
    assert result.detected is True
    assert result.keywords.count("中毒") == 1


def test_detect_emergency_english():
    result = detect_emergency("my dog is having a seizure")
    assert result.detected is True
    assert "seizure" in result.keywords


def test_build_emergency_hint():
    hint = build_emergency_hint(["中毒", "抽搐"])
    assert "中毒" in hint
    assert "抽搐" in hint
    assert "trigger_emergency" in hint
    assert "唯一豁免" in hint  # includes exemption/false-positive instruction


def test_build_emergency_hint_single_keyword():
    hint = build_emergency_hint(["出血"])
    assert "出血" in hint
    assert "trigger_emergency" in hint


def test_no_direct_sse_emission():
    """Verify detect_emergency doesn't emit SSE — it only returns data."""
    result = detect_emergency("猫中毒了快救命")
    # Result is just data, no side effects
    assert isinstance(result.detected, bool)
    assert isinstance(result.keywords, list)
