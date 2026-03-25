"""Tests for emergency keyword detection."""

import pytest

from app.agents.emergency import EMERGENCY_KEYWORDS, detect_emergency


class TestDetectEmergency:
    """Test emergency detection with various inputs."""

    @pytest.mark.parametrize("keyword", EMERGENCY_KEYWORDS)
    def test_detects_each_keyword(self, keyword: str):
        """Every keyword in the list should trigger detection."""
        message = f"My dog is experiencing {keyword} right now"
        assert detect_emergency(message).detected is True

    def test_case_insensitive(self):
        assert detect_emergency("My cat is having a SEIZURE").detected is True
        assert detect_emergency("CHOKING on a bone").detected is True
        assert detect_emergency("Difficulty Breathing after exercise").detected is True

    def test_keyword_in_longer_sentence(self):
        assert detect_emergency("I think my puppy swallowed a sock yesterday").detected is True
        assert detect_emergency("There's heavy bleeding from the paw").detected is True

    def test_no_emergency_normal_messages(self):
        assert detect_emergency("How much should I feed my dog?").detected is False
        assert detect_emergency("What vaccines does my puppy need?").detected is False
        assert detect_emergency("Best food for a golden retriever").detected is False
        assert detect_emergency("My dog is happy and healthy").detected is False

    def test_empty_message(self):
        assert detect_emergency("").detected is False

    def test_multiple_keywords(self):
        result = detect_emergency("My dog is having a seizure and bleeding")
        assert result.detected is True
        assert len(result.keywords) >= 2

    def test_multi_word_keywords(self):
        """Multi-word keywords like 'hit by car' should be detected."""
        assert detect_emergency("My dog was hit by car on the street").detected is True
        assert detect_emergency("allergic reaction to bee").detected is True
        assert detect_emergency("electric shock from chewing wire").detected is True
        assert detect_emergency("snake bite on the leg").detected is True
        assert detect_emergency("difficulty breathing at night").detected is True
        assert detect_emergency("not breathing anymore").detected is True
