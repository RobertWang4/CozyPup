"""Tests for Chat Agent and tool definitions/execution."""

import json
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agents.chat_agent import ChatAgent
from app.agents.tools import TOOL_DEFINITIONS, execute_tool
from app.database import Base
from app.models import CalendarEvent, EventCategory, EventSource, EventType, Pet, User



# ---------- DB fixtures (in-memory SQLite) ----------

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
async def db(async_engine):
    session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest_asyncio.fixture
async def test_user(db: AsyncSession, user_id):
    user = User(id=user_id, email="test@example.com", auth_provider="dev")
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def test_pet(db: AsyncSession, test_user):
    pet = Pet(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="Buddy",
        species="dog",
        breed="Golden Retriever",
        color_hex="E8835C",
    )
    db.add(pet)
    await db.flush()
    return pet


# ---------- Tool definition tests ----------


class TestToolDefinitions:
    def test_definitions_are_list(self):
        assert isinstance(TOOL_DEFINITIONS, list)
        assert len(TOOL_DEFINITIONS) == 9

    def test_all_tool_names(self):
        names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
        expected = [
            "create_calendar_event", "query_calendar_events",
            "update_calendar_event",
            "create_pet", "update_pet_profile", "list_pets",
            "create_reminder", "search_places", "draft_email",
        ]
        assert names == expected

    def test_create_event_definition_structure(self):
        create_tool = TOOL_DEFINITIONS[0]
        assert create_tool["type"] == "function"
        fn = create_tool["function"]
        assert fn["name"] == "create_calendar_event"
        assert "description" in fn
        params = fn["parameters"]
        assert params["type"] == "object"
        assert "pet_id" in params["properties"]
        assert "event_date" in params["properties"]
        assert "title" in params["properties"]
        assert "category" in params["properties"]
        assert set(params["required"]) == {"pet_id", "event_date", "title", "category"}

    def test_query_events_definition_structure(self):
        query_tool = TOOL_DEFINITIONS[1]
        assert query_tool["type"] == "function"
        fn = query_tool["function"]
        assert fn["name"] == "query_calendar_events"
        assert "description" in fn
        params = fn["parameters"]
        assert params["type"] == "object"
        assert "pet_id" in params["properties"]
        assert "start_date" in params["properties"]
        assert params["required"] == []

    def test_category_enum_values(self):
        create_fn = TOOL_DEFINITIONS[0]["function"]
        cat_enum = create_fn["parameters"]["properties"]["category"]["enum"]
        expected = ["diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"]
        assert cat_enum == expected


# ---------- Tool execution tests ----------


class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_create_calendar_event(self, db, test_pet, user_id):
        args = {
            "pet_id": str(test_pet.id),
            "event_date": "2026-03-19",
            "title": "Fed 200g kibble",
            "category": "diet",
            "raw_text": "I just fed Buddy 200g of kibble",
        }
        result = await execute_tool("create_calendar_event", args, db, user_id)

        assert result["success"] is True
        assert result["title"] == "Fed 200g kibble"
        assert result["category"] == "diet"
        assert "event_id" in result
        assert "card" in result
        assert result["card"]["type"] == "record"
        assert result["card"]["pet_name"] == "Buddy"

        # Verify the event was actually created in the DB
        event_id = uuid.UUID(result["event_id"])
        evt = await db.get(CalendarEvent, event_id)
        assert evt is not None
        assert evt.title == "Fed 200g kibble"
        assert evt.category == EventCategory.diet
        assert evt.source == EventSource.chat
        assert evt.edited is False
        assert evt.type == EventType.log

    @pytest.mark.asyncio
    async def test_create_calendar_event_with_time(self, db, test_pet, user_id):
        args = {
            "pet_id": str(test_pet.id),
            "event_date": "2026-03-19",
            "title": "Morning walk",
            "category": "daily",
            "event_time": "08:30",
        }
        result = await execute_tool("create_calendar_event", args, db, user_id)
        assert result["success"] is True

        evt = await db.get(CalendarEvent, uuid.UUID(result["event_id"]))
        assert evt.event_time is not None
        assert evt.event_time.hour == 8
        assert evt.event_time.minute == 30

    @pytest.mark.asyncio
    async def test_query_calendar_events_empty(self, db, user_id, test_user):
        result = await execute_tool("query_calendar_events", {}, db, user_id)
        assert result["count"] == 0
        assert result["events"] == []

    @pytest.mark.asyncio
    async def test_query_calendar_events_with_data(self, db, test_pet, user_id):
        # Create an event first
        await execute_tool(
            "create_calendar_event",
            {
                "pet_id": str(test_pet.id),
                "event_date": "2026-03-19",
                "title": "Ate breakfast",
                "category": "diet",
            },
            db,
            user_id,
        )

        # Query it
        result = await execute_tool(
            "query_calendar_events",
            {"pet_id": str(test_pet.id), "category": "diet"},
            db,
            user_id,
        )
        assert result["count"] == 1
        assert result["events"][0]["title"] == "Ate breakfast"
        assert result["events"][0]["category"] == "diet"

    @pytest.mark.asyncio
    async def test_query_calendar_events_date_filter(self, db, test_pet, user_id):
        # Create events on different dates
        for d in ["2026-03-17", "2026-03-18", "2026-03-19"]:
            await execute_tool(
                "create_calendar_event",
                {
                    "pet_id": str(test_pet.id),
                    "event_date": d,
                    "title": f"Event on {d}",
                    "category": "daily",
                },
                db,
                user_id,
            )

        result = await execute_tool(
            "query_calendar_events",
            {"start_date": "2026-03-18", "end_date": "2026-03-19"},
            db,
            user_id,
        )
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_execute_tool_unknown_name(self, db, user_id):
        with pytest.raises(ValueError, match="Unknown tool"):
            await execute_tool("nonexistent_tool", {}, db, user_id)


# ---------- ChatAgent tests ----------


def _make_stream_chunk(content=None, tool_calls=None, finish_reason=None):
    """Helper to create a mock streaming chunk."""
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _make_tool_call_delta(index, tc_id=None, fn_name=None, fn_arguments=None):
    """Helper to create a tool_call delta in a streaming chunk."""
    fn = SimpleNamespace(
        name=fn_name,
        arguments=fn_arguments,
    )
    return SimpleNamespace(index=index, id=tc_id, function=fn)


class TestChatAgent:
    @pytest.mark.asyncio
    async def test_simple_text_response(self, db, user_id, test_user):
        """Test that ChatAgent streams a simple text response."""
        agent = ChatAgent()

        # Mock streaming response: three text chunks
        async def mock_stream():
            yield _make_stream_chunk(content="Hello ")
            yield _make_stream_chunk(content="there!")
            yield _make_stream_chunk(content=None, finish_reason="stop")

        with patch("app.agents.chat_agent.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_stream())

            tokens = []
            result = await agent._run(
                "Hi",
                {
                    "system_prompt": "You are a helpful assistant.",
                    "context_messages": [],
                    "db": db,
                    "user_id": user_id,
                    "session_id": uuid.uuid4(),
                },
                on_token=lambda t: tokens.append(t),
            )

        assert result["response"] == "Hello there!"
        assert result["intent"] == "chat"
        assert result["cards"] == []
        assert tokens == ["Hello ", "there!"]

    @pytest.mark.asyncio
    async def test_tool_call_creates_event(self, db, test_pet, user_id):
        """Test that ChatAgent handles tool calls and creates calendar events."""
        agent = ChatAgent()
        pet_id = str(test_pet.id)

        tool_call_id = "call_abc123"
        tool_args = json.dumps({
            "pet_id": pet_id,
            "event_date": "2026-03-19",
            "title": "Vomited twice",
            "category": "abnormal",
        })

        # First LLM call: returns a tool call (no text)
        async def mock_stream_with_tool():
            yield _make_stream_chunk(
                tool_calls=[_make_tool_call_delta(0, tc_id=tool_call_id, fn_name="create_calendar_event", fn_arguments=tool_args)]
            )
            yield _make_stream_chunk(content=None, finish_reason="stop")

        # Second LLM call: returns text after tool result
        async def mock_stream_after_tool():
            yield _make_stream_chunk(content="I've recorded that Buddy vomited twice.")
            yield _make_stream_chunk(content=None, finish_reason="stop")

        call_count = 0

        async def mock_acompletion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_stream_with_tool()
            else:
                return mock_stream_after_tool()

        with patch("app.agents.chat_agent.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=mock_acompletion)

            cards_received = []
            result = await agent._run(
                "Buddy just vomited twice",
                {
                    "system_prompt": "You are a helpful assistant.",
                    "context_messages": [],
                    "db": db,
                    "user_id": user_id,
                    "session_id": uuid.uuid4(),
                },
                on_card=lambda c: cards_received.append(c),
            )

        assert result["intent"] == "chat"
        assert "recorded" in result["response"].lower()
        assert len(result["cards"]) == 1
        assert result["cards"][0]["type"] == "record"
        assert result["cards"][0]["pet_name"] == "Buddy"
        assert result["cards"][0]["category"] == "abnormal"
        assert cards_received == result["cards"]

        # Verify DB event was created
        db_result = await db.execute(
            select(CalendarEvent).where(CalendarEvent.user_id == user_id)
        )
        events = db_result.scalars().all()
        assert len(events) == 1
        assert events[0].title == "Vomited twice"

    @pytest.mark.asyncio
    async def test_tool_call_error_continues(self, db, user_id, test_user):
        """Test that ChatAgent gracefully handles tool execution errors."""
        agent = ChatAgent()

        tool_call_id = "call_err"
        # Invalid pet_id will cause an error
        tool_args = json.dumps({
            "pet_id": str(uuid.uuid4()),
            "event_date": "2026-03-19",
            "title": "Test",
            "category": "daily",
        })

        async def mock_stream_tool():
            yield _make_stream_chunk(
                tool_calls=[_make_tool_call_delta(0, tc_id=tool_call_id, fn_name="create_calendar_event", fn_arguments=tool_args)]
            )
            yield _make_stream_chunk(content=None, finish_reason="stop")

        async def mock_stream_recovery():
            yield _make_stream_chunk(content="I had trouble recording that.")
            yield _make_stream_chunk(content=None, finish_reason="stop")

        call_count = 0

        async def mock_acompletion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_stream_tool()
            return mock_stream_recovery()

        with patch("app.agents.chat_agent.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=mock_acompletion)

            result = await agent._run(
                "test",
                {
                    "system_prompt": "You are a helpful assistant.",
                    "context_messages": [],
                    "db": db,
                    "user_id": user_id,
                    "session_id": uuid.uuid4(),
                },
            )

        # Should still get a response even if tool errored
        assert result["response"] != ""
        assert result["intent"] == "chat"

    @pytest.mark.asyncio
    async def test_passes_tools_to_litellm(self, db, user_id, test_user):
        """Test that TOOL_DEFINITIONS are passed to the LLM call."""
        agent = ChatAgent()

        async def mock_stream():
            yield _make_stream_chunk(content="Hi!")
            yield _make_stream_chunk(content=None, finish_reason="stop")

        with patch("app.agents.chat_agent.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_stream())

            await agent._run(
                "Hello",
                {
                    "system_prompt": "test",
                    "context_messages": [],
                    "db": db,
                    "user_id": user_id,
                    "session_id": uuid.uuid4(),
                },
            )

            call_kwargs = mock_litellm.acompletion.call_args
            assert call_kwargs.kwargs["tools"] == TOOL_DEFINITIONS
            assert call_kwargs.kwargs["stream"] is True


# ---------- CreatePet tool tests ----------


class TestCreatePetTool:
    @pytest.mark.asyncio
    async def test_create_pet_basic(self, db, test_user, user_id):
        result = await execute_tool(
            "create_pet",
            {"name": "Luna", "species": "cat", "breed": "Persian"},
            db,
            user_id,
        )
        assert result["success"] is True
        assert result["pet_name"] == "Luna"
        assert result["card"]["type"] == "pet_created"

    @pytest.mark.asyncio
    async def test_create_pet_with_gender_and_extras(self, db, test_user, user_id):
        result = await execute_tool(
            "create_pet",
            {
                "name": "Max",
                "species": "dog",
                "breed": "Husky",
                "gender": "male",
                "neutered": True,
                "coat_color": "white",
                "birthday": "2024-06-15",
                "weight": 25.0,
            },
            db,
            user_id,
        )
        assert result["success"] is True
        pet_id = uuid.UUID(result["pet_id"])
        pet = await db.get(Pet, pet_id)
        assert pet.profile["gender"] == "male"
        assert pet.profile["neutered"] is True
        assert pet.profile["coat_color"] == "white"
        assert pet.birthday == date(2024, 6, 15)
        assert pet.weight == 25.0


class TestSearchPlacesTool:
    @pytest.mark.asyncio
    async def test_search_places_no_location(self, db, user_id, test_user):
        result = await execute_tool(
            "search_places",
            {"query": "vet clinic"},
            db,
            user_id,
            location=None,
        )
        assert result["success"] is False
        assert "location" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_search_places_with_location(self, db, user_id, test_user):
        mock_places = [
            {"name": "Happy Vet", "address": "123 Main St", "rating": 4.5, "lat": 31.23, "lng": 121.47, "place_id": "abc", "open_now": True},
        ]
        with patch("app.services.places.places_service") as mock_svc:
            mock_svc.search_nearby = AsyncMock(return_value=mock_places)
            result = await execute_tool(
                "search_places",
                {"query": "veterinary clinic"},
                db,
                user_id,
                location={"lat": 31.23, "lng": 121.47},
            )
        assert result["success"] is True
        assert result["card"]["type"] == "map"
        assert len(result["card"]["places"]) == 1


class TestDraftEmailTool:
    @pytest.mark.asyncio
    async def test_draft_email(self, db, user_id, test_user):
        result = await execute_tool(
            "draft_email",
            {
                "subject": "Appointment for Buddy",
                "body": "Dear Dr. Smith,\n\nI would like to book an appointment...",
            },
            db,
            user_id,
        )
        assert result["success"] is True
        assert result["card"]["type"] == "email"
        assert result["card"]["subject"] == "Appointment for Buddy"
