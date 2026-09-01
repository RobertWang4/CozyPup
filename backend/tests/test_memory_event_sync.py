import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.memory import event_sync


@pytest.mark.asyncio
async def test_sync_event_memory_uses_event_date_for_recency(monkeypatch):
    captured = {}
    event_id = uuid.uuid4()
    user_id = uuid.uuid4()
    pet_id = uuid.uuid4()
    event = SimpleNamespace(
        id=event_id,
        user_id=user_id,
        pet_id=pet_id,
        category=SimpleNamespace(value="medical"),
        title="去年打疫苗",
        raw_text="补录去年的疫苗",
        notes=None,
        event_date=date(2025, 3, 2),
        created_at=datetime(2026, 6, 14, 12, 0, tzinfo=UTC),
    )

    class Result:
        def scalar_one_or_none(self):
            return event

    class FakeDb:
        async def execute(self, stmt):
            return Result()

    class FakeSession:
        async def __aenter__(self):
            return FakeDb()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_upsert_behavioral_memory(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(event_sync, "async_session", lambda: FakeSession())
    monkeypatch.setattr(event_sync, "upsert_behavioral_memory", fake_upsert_behavioral_memory)

    await event_sync.sync_event_memory(event_id)

    assert captured["occurred_at"] == datetime(2025, 3, 2, tzinfo=UTC)
