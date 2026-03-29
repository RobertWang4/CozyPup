"""Tests for tool argument validation."""

import pytest

from app.agents.validation import validate_tool_args


class TestValidateToolArgs:
    def test_valid_create_calendar_event(self):
        args = {
            "pet_id": "550e8400-e29b-41d4-a716-446655440000",
            "event_date": "2026-03-22",
            "title": "Fed kibble",
            "category": "diet",
        }
        errors = validate_tool_args("create_calendar_event", args)
        assert errors == []

    def test_missing_required_field(self):
        args = {"pet_id": "550e8400-e29b-41d4-a716-446655440000", "title": "Test"}
        errors = validate_tool_args("create_calendar_event", args)
        assert any("event_date" in e for e in errors)
        assert any("category" in e for e in errors)

    def test_invalid_date_format(self):
        args = {
            "pet_id": "550e8400-e29b-41d4-a716-446655440000",
            "event_date": "March 22",
            "title": "Test",
            "category": "diet",
        }
        errors = validate_tool_args("create_calendar_event", args)
        assert any("date" in e.lower() for e in errors)

    def test_invalid_uuid(self):
        args = {
            "pet_id": "not-a-uuid",
            "event_date": "2026-03-22",
            "title": "Test",
            "category": "diet",
        }
        errors = validate_tool_args("create_calendar_event", args)
        assert any("uuid" in e.lower() for e in errors)

    def test_invalid_category(self):
        args = {
            "pet_id": "550e8400-e29b-41d4-a716-446655440000",
            "event_date": "2026-03-22",
            "title": "Test",
            "category": "swimming",
        }
        errors = validate_tool_args("create_calendar_event", args)
        assert any("category" in e.lower() for e in errors)

    def test_removed_categories_rejected(self):
        """Old categories (excretion, vaccine, deworming) should be rejected."""
        for old_cat in ["excretion", "vaccine", "deworming"]:
            args = {
                "pet_id": "550e8400-e29b-41d4-a716-446655440000",
                "event_date": "2026-03-22",
                "title": "Test",
                "category": old_cat,
            }
            errors = validate_tool_args("create_calendar_event", args)
            assert any("category" in e.lower() for e in errors), (
                f"Old category '{old_cat}' should be rejected"
            )

    def test_new_category_set(self):
        """Valid categories are: daily, diet, medical, abnormal."""
        for cat in ["daily", "diet", "medical", "abnormal"]:
            args = {
                "pet_id": "550e8400-e29b-41d4-a716-446655440000",
                "event_date": "2026-03-22",
                "title": "Test",
                "category": cat,
            }
            errors = validate_tool_args("create_calendar_event", args)
            assert errors == [], f"Category '{cat}' should be valid, got {errors}"

    def test_valid_create_pet(self):
        errors = validate_tool_args("create_pet", {"name": "Buddy", "species": "dog"})
        assert errors == []

    def test_invalid_species(self):
        errors = validate_tool_args("create_pet", {"name": "Buddy", "species": "fish"})
        assert any("species" in e.lower() for e in errors)

    def test_valid_create_reminder(self):
        args = {
            "pet_id": "550e8400-e29b-41d4-a716-446655440000",
            "type": "medication",
            "title": "Give meds",
            "trigger_at": "2026-03-22T10:00:00",
        }
        errors = validate_tool_args("create_reminder", args)
        assert errors == []

    def test_invalid_reminder_trigger_at(self):
        args = {
            "pet_id": "550e8400-e29b-41d4-a716-446655440000",
            "type": "medication",
            "title": "Give meds",
            "trigger_at": "tomorrow 10am",
        }
        errors = validate_tool_args("create_reminder", args)
        assert any("trigger_at" in e for e in errors)

    def test_unknown_tool_passes(self):
        errors = validate_tool_args("unknown_tool", {"anything": "goes"})
        assert errors == []

    def test_valid_time_format(self):
        args = {
            "pet_id": "550e8400-e29b-41d4-a716-446655440000",
            "event_date": "2026-03-22",
            "title": "Walk",
            "category": "daily",
            "event_time": "08:30",
        }
        errors = validate_tool_args("create_calendar_event", args)
        assert errors == []

    def test_invalid_time_format(self):
        args = {
            "pet_id": "550e8400-e29b-41d4-a716-446655440000",
            "event_date": "2026-03-22",
            "title": "Walk",
            "category": "daily",
            "event_time": "8am",
        }
        errors = validate_tool_args("create_calendar_event", args)
        assert any("time" in e.lower() for e in errors)
