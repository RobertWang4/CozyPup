import pytest
import sqlalchemy as sa
from app.models import CalendarEvent


class TestCalendarEventPhotos:
    def test_photos_column_exists(self):
        """CalendarEvent has a photos column of type JSON."""
        col = CalendarEvent.__table__.c.photos
        assert isinstance(col.type, sa.JSON)
        assert col.server_default.arg == "[]"

    def test_photos_default_empty(self):
        """CalendarEvent.photos defaults to empty list when explicitly set."""
        evt = CalendarEvent(
            user_id="test", pet_id="test",
            event_date="2026-03-22", title="Test",
            photos=[],
        )
        assert evt.photos == []

    def test_photos_stores_urls(self):
        """CalendarEvent.photos can store a list of URL strings."""
        urls = ["https://example.com/photo1.jpg", "https://example.com/photo2.jpg"]
        evt = CalendarEvent(
            user_id="test", pet_id="test",
            event_date="2026-03-22", title="Test",
            photos=urls,
        )
        assert evt.photos == urls
        assert len(evt.photos) == 2
