"""Tests for calendar event photo upload and serve endpoints."""

import io
import uuid
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth import get_current_user_id
from app.database import Base, get_db
from app.main import app
from app.models import CalendarEvent, EventCategory, EventSource, EventType, Pet, User


# ---------- DB fixtures (in-memory SQLite) ----------

TEST_USER_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine):
    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    user = User(id=TEST_USER_ID, email="test@example.com", auth_provider="dev")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_pet(db_session: AsyncSession, test_user):
    pet = Pet(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="Buddy",
        species="dog",
        color_hex="E8835C",
    )
    db_session.add(pet)
    await db_session.flush()
    return pet


@pytest_asyncio.fixture
async def test_event(db_session: AsyncSession, test_pet, test_user):
    event = CalendarEvent(
        id=uuid.uuid4(),
        user_id=test_user.id,
        pet_id=test_pet.id,
        event_date=date(2026, 3, 22),
        title="Walk in the park",
        type=EventType.log,
        category=EventCategory.daily,
        raw_text="Walk in the park",
        source=EventSource.manual,
    )
    db_session.add(event)
    await db_session.commit()
    return event


@pytest.fixture
def client(db_session: AsyncSession):
    async def override_get_db():
        yield db_session

    async def override_get_current_user_id():
        return TEST_USER_ID

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = override_get_current_user_id
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _make_jpeg_bytes(size: int = 100) -> bytes:
    """Create minimal valid-ish JPEG bytes of a given size."""
    # Just enough bytes for testing; not a real image but the endpoint only checks MIME type
    return b"\xff\xd8\xff\xe0" + b"\x00" * (size - 4)


class TestUploadPhoto:
    def test_upload_photo_to_event(self, client, test_event, tmp_path):
        with patch("app.routers.calendar.PHOTO_DIR", tmp_path):
            file_content = _make_jpeg_bytes(1024)
            response = client.post(
                f"/api/v1/calendar/{test_event.id}/photos",
                files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")},
            )
        assert response.status_code == 200
        data = response.json()
        assert len(data["photos"]) == 1
        assert data["photos"][0].startswith("/api/v1/calendar/photos/")
        assert data["photos"][0].endswith(".jpg")

    def test_upload_exceeds_max_photos(self, client, test_event, db_session, tmp_path):
        with patch("app.routers.calendar.PHOTO_DIR", tmp_path):
            # Upload 4 photos (the max)
            for i in range(4):
                file_content = _make_jpeg_bytes(512)
                resp = client.post(
                    f"/api/v1/calendar/{test_event.id}/photos",
                    files={
                        "file": (
                            f"photo{i}.jpg",
                            io.BytesIO(file_content),
                            "image/jpeg",
                        )
                    },
                )
                assert resp.status_code == 200, f"Upload {i} failed: {resp.text}"

            # 5th should fail
            file_content = _make_jpeg_bytes(512)
            response = client.post(
                f"/api/v1/calendar/{test_event.id}/photos",
                files={
                    "file": ("photo5.jpg", io.BytesIO(file_content), "image/jpeg")
                },
            )
        assert response.status_code == 400
        assert "Maximum" in response.json()["detail"]

    def test_upload_invalid_mime_type(self, client, test_event, tmp_path):
        with patch("app.routers.calendar.PHOTO_DIR", tmp_path):
            response = client.post(
                f"/api/v1/calendar/{test_event.id}/photos",
                files={
                    "file": (
                        "test.gif",
                        io.BytesIO(b"GIF89a" + b"\x00" * 100),
                        "image/gif",
                    )
                },
            )
        assert response.status_code == 400
        assert "Only JPEG, PNG, and WebP" in response.json()["detail"]

    def test_upload_to_nonexistent_event(self, client, tmp_path):
        fake_id = uuid.uuid4()
        with patch("app.routers.calendar.PHOTO_DIR", tmp_path):
            response = client.post(
                f"/api/v1/calendar/{fake_id}/photos",
                files={
                    "file": (
                        "test.jpg",
                        io.BytesIO(_make_jpeg_bytes(100)),
                        "image/jpeg",
                    )
                },
            )
        assert response.status_code == 404


class TestGetPhoto:
    def test_get_photo(self, client, tmp_path):
        # Write a file to the photo dir
        filename = f"{uuid.uuid4()}.jpg"
        photo_content = _make_jpeg_bytes(256)
        (tmp_path / filename).write_bytes(photo_content)

        with patch("app.routers.calendar.PHOTO_DIR", tmp_path):
            response = client.get(f"/api/v1/calendar/photos/{filename}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content == photo_content

    def test_get_nonexistent_photo(self, client, tmp_path):
        with patch("app.routers.calendar.PHOTO_DIR", tmp_path):
            response = client.get("/api/v1/calendar/photos/nonexistent.jpg")
        assert response.status_code == 404
