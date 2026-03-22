# Constrained Agent Refactor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor from router + multi-agent pattern to unified ChatAgent with validation layer, per the spec at `docs/superpowers/specs/2026-03-17-petcare-agent-design.md`.

**Architecture:** Single ChatAgent handles all intents (chat, map, email, summary) via function calling. Remove the LLM-based intent router and 3 standalone agents. Add schema validation between LLM output and tool execution with error feedback for retries.

**Tech Stack:** FastAPI, LiteLLM, SQLAlchemy async, Google Places API, SSE streaming

---

### Task 1: Fix Gender bug in create_pet

**Files:**
- Modify: `backend/app/agents/tools.py:311-360`
- Test: `backend/tests/test_chat_agent.py`

The `_create_pet` function references an undefined `Gender` enum (line 330) and tries to set `gender`, `neutered`, `coat_color` as Pet columns — but Pet model only has `profile` JSON for flexible data.

- [ ] **Step 1: Write test for create_pet via tool execution**

Add to `backend/tests/test_chat_agent.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_chat_agent.py::TestCreatePetTool -v`
Expected: FAIL — `NameError: name 'Gender' is not defined`

- [ ] **Step 3: Fix _create_pet to store extras in profile JSON**

In `backend/app/agents/tools.py`, replace `_create_pet` (lines 311-360):

```python
async def _create_pet(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Create a new pet profile."""
    name = arguments["name"]
    species = Species(arguments["species"])
    breed = arguments.get("breed", "")
    birthday_str = arguments.get("birthday")
    weight = arguments.get("weight")

    # Auto-assign color
    count_result = await db.execute(
        select(func.count()).where(Pet.user_id == user_id)
    )
    count = count_result.scalar() or 0
    color = PET_COLORS[count % len(PET_COLORS)]

    pet = Pet(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        species=species,
        breed=breed,
        birthday=date.fromisoformat(birthday_str) if birthday_str else None,
        weight=weight,
        color_hex=color,
    )

    # Store optional fields in flexible profile JSON
    profile = {}
    for key in ("gender", "neutered", "coat_color"):
        if key in arguments:
            profile[key] = arguments[key]
    if profile:
        pet.profile = profile

    db.add(pet)
    await db.flush()

    card = {
        "type": "pet_created",
        "pet_name": name,
        "species": arguments["species"],
        "breed": breed,
    }

    return {
        "success": True,
        "pet_id": str(pet.id),
        "pet_name": name,
        "species": arguments["species"],
        "card": card,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_chat_agent.py::TestCreatePetTool -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/tools.py backend/tests/test_chat_agent.py
git commit -m "fix: store gender/neutered/coat_color in Pet.profile JSON instead of undefined columns"
```

---

### Task 2: Add schema validation layer

**Files:**
- Create: `backend/app/agents/validation.py`
- Modify: `backend/app/agents/chat_agent.py:78-103`
- Test: `backend/tests/test_validation.py`

Add a validation layer between LLM tool call output and executor. On failure, the error message goes back to the LLM as the tool result so it can retry (up to MAX_TOOL_ROUNDS).

- [ ] **Step 1: Write validation tests**

Create `backend/tests/test_validation.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.validation'`

- [ ] **Step 3: Implement validation module**

Create `backend/app/agents/validation.py`:

```python
"""Schema validation for tool call arguments.

Validates LLM-generated arguments before they reach the executor.
Returns a list of human-readable error strings (empty = valid).
Errors are fed back to the LLM so it can retry.
"""

import re
import uuid
from datetime import date, datetime

# Enum values from TOOL_DEFINITIONS (source of truth: tools.py)
_CATEGORIES = {"diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"}
_SPECIES = {"dog", "cat", "other"}
_REMINDER_TYPES = {"medication", "vaccine", "checkup", "feeding", "grooming", "other"}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _check_required(args: dict, fields: list[str]) -> list[str]:
    return [f"Missing required field: {f}" for f in fields if f not in args]


def _check_uuid(args: dict, field: str) -> list[str]:
    val = args.get(field)
    if val is None:
        return []
    try:
        uuid.UUID(str(val))
        return []
    except ValueError:
        return [f"Invalid UUID for {field}: {val!r}"]


def _check_date(args: dict, field: str) -> list[str]:
    val = args.get(field)
    if val is None:
        return []
    if not _DATE_RE.match(str(val)):
        return [f"Invalid date format for {field}: {val!r} (expected YYYY-MM-DD)"]
    try:
        date.fromisoformat(str(val))
        return []
    except ValueError:
        return [f"Invalid date for {field}: {val!r}"]


def _check_time(args: dict, field: str) -> list[str]:
    val = args.get(field)
    if val is None:
        return []
    if not _TIME_RE.match(str(val)):
        return [f"Invalid time format for {field}: {val!r} (expected HH:MM)"]
    return []


def _check_datetime(args: dict, field: str) -> list[str]:
    val = args.get(field)
    if val is None:
        return []
    try:
        datetime.fromisoformat(str(val))
        return []
    except ValueError:
        return [f"Invalid datetime for {field}: {val!r} (expected ISO 8601, e.g. 2026-03-22T10:00:00)"]


def _check_enum(args: dict, field: str, valid: set[str], label: str) -> list[str]:
    val = args.get(field)
    if val is None:
        return []
    if str(val) not in valid:
        return [f"Invalid {label} for {field}: {val!r} (must be one of: {', '.join(sorted(valid))})"]
    return []


# Per-tool validation rules
_VALIDATORS: dict[str, callable] = {}


def _register(name: str):
    def decorator(fn):
        _VALIDATORS[name] = fn
        return fn
    return decorator


@_register("create_calendar_event")
def _validate_create_calendar_event(args: dict) -> list[str]:
    errors = _check_required(args, ["pet_id", "event_date", "title", "category"])
    errors += _check_uuid(args, "pet_id")
    errors += _check_date(args, "event_date")
    errors += _check_enum(args, "category", _CATEGORIES, "category")
    errors += _check_time(args, "event_time")
    return errors


@_register("query_calendar_events")
def _validate_query_calendar_events(args: dict) -> list[str]:
    errors = _check_uuid(args, "pet_id")
    errors += _check_date(args, "start_date")
    errors += _check_date(args, "end_date")
    errors += _check_enum(args, "category", _CATEGORIES, "category")
    return errors


@_register("create_pet")
def _validate_create_pet(args: dict) -> list[str]:
    errors = _check_required(args, ["name", "species"])
    errors += _check_enum(args, "species", _SPECIES, "species")
    errors += _check_date(args, "birthday")
    return errors


@_register("update_pet_profile")
def _validate_update_pet_profile(args: dict) -> list[str]:
    errors = _check_required(args, ["pet_id", "info"])
    errors += _check_uuid(args, "pet_id")
    return errors


@_register("list_pets")
def _validate_list_pets(args: dict) -> list[str]:
    return []


@_register("create_reminder")
def _validate_create_reminder(args: dict) -> list[str]:
    errors = _check_required(args, ["pet_id", "type", "title", "trigger_at"])
    errors += _check_uuid(args, "pet_id")
    errors += _check_enum(args, "type", _REMINDER_TYPES, "reminder type")
    errors += _check_datetime(args, "trigger_at")
    return errors


def validate_tool_args(tool_name: str, arguments: dict) -> list[str]:
    """Validate tool arguments against the schema.

    Args:
        tool_name: Name of the tool being called.
        arguments: Parsed argument dict from LLM.

    Returns:
        List of error strings. Empty list means valid.
    """
    validator = _VALIDATORS.get(tool_name)
    if validator is None:
        return []  # Unknown tools pass through (fail at executor)
    return validator(arguments)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_validation.py -v`
Expected: PASS

- [ ] **Step 5: Wire validation into ChatAgent**

In `backend/app/agents/chat_agent.py`, add the import and validation call.

Add import at top:
```python
from app.agents.validation import validate_tool_args
```

Replace the tool execution block (lines 79-110) with:

```python
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError as exc:
                    logger.warning("tool_args_json_error", extra={"tool": fn_name, "error": str(exc)[:200]})
                    result = {"error": f"Invalid JSON in arguments: {exc}"}
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    })
                    continue

                logger.info(
                    "chat_agent_tool_call",
                    extra={"tool": fn_name, "round": _round},
                )

                # Schema validation — errors go back to LLM for retry
                validation_errors = validate_tool_args(fn_name, fn_args)
                if validation_errors:
                    logger.warning(
                        "tool_validation_failed",
                        extra={"tool": fn_name, "errors": validation_errors},
                    )
                    result = {"error": "Validation failed: " + "; ".join(validation_errors)}
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    })
                    continue

                try:
                    result = await execute_tool(fn_name, fn_args, db, user_id)

                    if "card" in result:
                        card = result["card"]
                        cards.append(card)
                        if on_card:
                            await _maybe_await(on_card, card)

                except Exception as exc:
                    logger.error(
                        "chat_agent_tool_error",
                        extra={"tool": fn_name, "error": str(exc)[:200]},
                    )
                    result = {"error": str(exc)}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result),
                })
```

- [ ] **Step 6: Run all existing tests**

Run: `cd backend && python -m pytest tests/test_chat_agent.py tests/test_validation.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/agents/validation.py backend/app/agents/chat_agent.py backend/tests/test_validation.py
git commit -m "feat: add schema validation layer between LLM tool calls and executor"
```

---

### Task 3: Add search_places and draft_email tools

**Files:**
- Modify: `backend/app/agents/tools.py`
- Modify: `backend/app/agents/validation.py`
- Test: `backend/tests/test_chat_agent.py`

Add these as function-calling tools so the ChatAgent can handle map and email intents directly.

- [ ] **Step 1: Write tests for new tools**

Add to `backend/tests/test_chat_agent.py`:

```python
from unittest.mock import patch, AsyncMock


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
        with patch("app.agents.tools.places_service") as mock_svc:
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_chat_agent.py::TestSearchPlacesTool tests/test_chat_agent.py::TestDraftEmailTool -v`
Expected: FAIL

- [ ] **Step 3: Add tool definitions to TOOL_DEFINITIONS**

Append to `TOOL_DEFINITIONS` list in `backend/app/agents/tools.py`:

```python
    {
        "type": "function",
        "function": {
            "name": "search_places",
            "description": (
                "Search for nearby pet-related places like veterinary clinics, pet stores, "
                "dog parks, groomers, or emergency animal hospitals. Use when the user asks "
                "to find a location or asks 'where can I...'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search query for Google Places, e.g. 'veterinary clinic', "
                            "'dog park', '24 hour emergency vet'."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_email",
            "description": (
                "Present a draft email as a card for the user to review and send. "
                "Use when the user asks to compose an email to a vet or pet professional. "
                "YOU write the email content based on conversation context, then call this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "Email subject line.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Full email body text.",
                    },
                },
                "required": ["subject", "body"],
            },
        },
    },
```

- [ ] **Step 4: Add executor functions and update execute_tool signature**

**Important:** The `places_service` import is lazy to avoid breaking all tools if the places module has issues (e.g., missing `httpx`).

Add executor functions to `backend/app/agents/tools.py`:

```python
async def _search_places(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    location: dict | None = None,
    **_kwargs,
) -> dict:
    """Search for nearby places via Google Places API."""
    if not location or "lat" not in location or "lng" not in location:
        return {
            "success": False,
            "error": "No location available. Ask the user to share their location.",
        }

    from app.services.places import places_service

    query = arguments["query"]
    places = await places_service.search_nearby(
        lat=location["lat"], lng=location["lng"], query=query
    )

    if not places:
        return {
            "success": True,
            "places": [],
            "message": f"No results found for '{query}' nearby.",
        }

    card = {
        "type": "map",
        "query": query,
        "places": [
            {
                "name": p["name"],
                "address": p["address"],
                "rating": p.get("rating"),
                "lat": p["lat"],
                "lng": p["lng"],
            }
            for p in places
        ],
    }

    return {
        "success": True,
        "places_count": len(places),
        "top_results": [f"{p['name']} — {p['address']}" for p in places[:5]],
        "card": card,
    }


async def _draft_email(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    **_kwargs,
) -> dict:
    """Wrap an email draft into a card for the frontend."""
    subject = arguments["subject"]
    body = arguments["body"]

    card = {
        "type": "email",
        "subject": subject,
        "body": body,
    }

    return {
        "success": True,
        "card": card,
    }
```

Update `_TOOL_HANDLERS`:
```python
_TOOL_HANDLERS = {
    "create_calendar_event": _create_calendar_event,
    "query_calendar_events": _query_calendar_events,
    "create_pet": _create_pet,
    "update_pet_profile": _update_pet_profile,
    "list_pets": _list_pets,
    "create_reminder": _create_reminder,
    "search_places": _search_places,
    "draft_email": _draft_email,
}
```

Update `execute_tool` to accept `**kwargs` but only forward them to tools that need extra context (search_places uses `location`). Use a set to track which tools accept kwargs:

```python
# Tools that accept extra kwargs (e.g., location)
_TOOLS_WITH_KWARGS = {"search_places"}


async def execute_tool(
    name: str,
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    **kwargs,
) -> dict:
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")

    logger.info("tool_execute", extra={"tool": name, "arguments_keys": list(arguments.keys())})
    try:
        if name in _TOOLS_WITH_KWARGS:
            result = await handler(arguments, db, user_id, **kwargs)
        else:
            result = await handler(arguments, db, user_id)
        logger.info("tool_success", extra={"tool": name})
        return result
    except Exception as exc:
        logger.error("tool_error", extra={"tool": name, "error": str(exc)[:200]})
        raise
```

- [ ] **Step 5: Fix tool count assertion in existing tests**

In `backend/tests/test_chat_agent.py`, update `TestToolDefinitions.test_definitions_are_list`:

```python
    def test_definitions_are_list(self):
        assert isinstance(TOOL_DEFINITIONS, list)
        assert len(TOOL_DEFINITIONS) == 8
```

Add a comprehensive name test:

```python
    def test_all_tool_names(self):
        names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
        expected = [
            "create_calendar_event", "query_calendar_events",
            "create_pet", "update_pet_profile", "list_pets",
            "create_reminder", "search_places", "draft_email",
        ]
        assert names == expected
```

- [ ] **Step 6: Add validation rules for new tools**

In `backend/app/agents/validation.py`, add:

```python
@_register("search_places")
def _validate_search_places(args: dict) -> list[str]:
    return _check_required(args, ["query"])


@_register("draft_email")
def _validate_draft_email(args: dict) -> list[str]:
    return _check_required(args, ["subject", "body"])
```

- [ ] **Step 7: Update ChatAgent to pass location to execute_tool**

In `backend/app/agents/chat_agent.py`, update the `_run` method to extract location from context and pass it through:

After `user_id = context["user_id"]` (line 48), add:
```python
        location = context.get("location")
```

Update the `execute_tool` call (inside the tool execution block) to:
```python
                    result = await execute_tool(fn_name, fn_args, db, user_id, location=location)
```

- [ ] **Step 8: Update _list_pets to return profile data**

Now that gender/extras live in `profile` JSON, `_list_pets` should return it so the LLM gets complete pet info. In `backend/app/agents/tools.py`, update the return dict in `_list_pets`:

```python
    return {
        "pets": [
            {
                "id": str(p.id),
                "name": p.name,
                "species": p.species.value,
                "breed": p.breed,
                "birthday": p.birthday.isoformat() if p.birthday else None,
                "weight": p.weight,
                "profile": p.profile or {},
            }
            for p in pets
        ],
        "count": len(pets),
    }
```

- [ ] **Step 9: Run tests**

Run: `cd backend && python -m pytest tests/test_chat_agent.py tests/test_validation.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add backend/app/agents/tools.py backend/app/agents/validation.py backend/app/agents/chat_agent.py backend/tests/test_chat_agent.py
git commit -m "feat: add search_places and draft_email as ChatAgent tools"
```

---

### Task 4: Update system prompt for unified agent

**Files:**
- Modify: `backend/app/agents/prompts.py`

Add search_places and draft_email tool instructions to CHAT_SYSTEM_PROMPT. Remove ROUTER_PROMPT, SUMMARY_PROMPT, EMAIL_PROMPT, MAP_PROMPT.

- [ ] **Step 1: Update CHAT_SYSTEM_PROMPT**

Replace `backend/app/agents/prompts.py` entirely:

```python
"""Prompt templates for the CozyPup Unified ChatAgent."""

CHAT_SYSTEM_PROMPT = """You are CozyPup, a friendly and knowledgeable pet health assistant.
You help pet owners with health questions, care tips, and general pet wellness guidance.

Today's date: {today_date}

Important rules:
- Always be warm, supportive, and encouraging.
- For health-related questions, provide helpful guidance but always recommend consulting a veterinarian for serious concerns.
- End health-related responses with: "This is general guidance only and not a substitute for professional veterinary advice."
- You MUST respond in the same language the user uses. If the user writes in Chinese, respond entirely in Chinese. If in English, respond in English. Match the user's language exactly.
- Keep responses concise and practical.

## Tools

You have access to the following tools. You MUST call the appropriate tool when the user's request matches — do NOT say you cannot do something if a matching tool exists.

### Pet Management
- **create_pet** — Create a new pet profile. You MUST call this when the user mentions they have a new pet, adopted a pet, or wants to add a pet. Example: "我又养了一只金毛叫豆豆" → call create_pet(name="豆豆", species="dog", breed="Golden Retriever").
- **update_pet_profile** — Save ANY info about a pet as flexible key-value pairs. Call this proactively whenever the user mentions details about their pet (gender, allergies, diet, vet, temperament, medical history, etc). This builds up the pet's profile over time through natural conversation.
- **list_pets** — List all registered pets. Call when you need pet IDs or the user asks about their pets.

### Calendar
- **create_calendar_event** — Record health events to the calendar. ONLY use when the user explicitly asks to record, add, or log something. Do NOT auto-record when the user is just describing symptoms or asking questions.
- **query_calendar_events** — Look up past health events when the user asks about history or trends.

### Reminders
- **create_reminder** — Set a push notification reminder. Call when the user asks to be reminded about medication, vet visits, feeding, etc.

### Location Search
- **search_places** — Find nearby vets, pet stores, dog parks, groomers, or emergency animal hospitals. Call when the user asks to find a place or asks "where can I...". You generate the search query based on the user's request and pet context.

### Email
- **draft_email** — Draft and present a professional email to a vet or pet service provider. When the user asks to write an email, YOU compose the subject and body using conversation context and pet info, then call this tool to present it as a card. Write the email in the same language the user is using.

## Multi-pet handling

The user may have multiple pets. Their pet profiles are listed below. When referring to a specific pet:
- If they specify which pet (by name), use that pet's ID.
- If there is only one pet, use that pet's ID.
- If there are multiple pets and it is ambiguous, ask the user to clarify.

## Critical rule

Always use tools to perform actions. Never describe what you would do — actually call the tool.

{pet_context}"""
```

- [ ] **Step 2: Run tests to check nothing broke**

Run: `cd backend && python -m pytest tests/ -v --ignore=tests/test_agents_router.py --ignore=tests/test_summary_agent.py --ignore=tests/test_map_agent.py --ignore=tests/test_email_agent.py`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/agents/prompts.py
git commit -m "refactor: unify system prompt for single ChatAgent, remove unused prompt templates"
```

---

### Task 5: Remove router and simplify chat endpoint

**Files:**
- Modify: `backend/app/routers/chat.py`

Remove intent routing and standalone agent dispatch. All messages go directly to ChatAgent.

- [ ] **Step 1: Rewrite chat.py**

Replace `backend/app/routers/chat.py` with:

```python
"""Chat SSE endpoint — streams LLM responses to the frontend."""

import asyncio
import json
import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agents.chat_agent import ChatAgent
from app.agents.emergency import detect_emergency
from app.agents.prompts import CHAT_SYSTEM_PROMPT
from app.auth import get_current_user_id
from app.database import get_db
from app.models import Chat, ChatSession, MessageRole, Pet

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chat"])

MAX_CONTEXT_MESSAGES = 20

_chat_agent = ChatAgent()


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    location: dict | None = None  # {"lat": float, "lng": float}
    language: str | None = None   # "zh", "en", or None (auto-detect from message)


async def _get_or_create_session(
    db: AsyncSession, user_id: uuid.UUID
) -> ChatSession:
    """Find today's session or create a new one."""
    today = date.today()
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.user_id == user_id,
            ChatSession.session_date == today,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        session = ChatSession(
            id=uuid.uuid4(), user_id=user_id, session_date=today
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
    return session


async def _get_pets(db: AsyncSession, user_id: uuid.UUID) -> list[Pet]:
    """Load all pets for the user."""
    result = await db.execute(
        select(Pet).where(Pet.user_id == user_id).order_by(Pet.created_at)
    )
    return list(result.scalars().all())


async def _build_pet_context(pets: list[Pet]) -> str:
    """Build pet profile context string for the system prompt."""
    if not pets:
        return "The user has not added any pets yet."

    lines = ["The user's pets:"]
    for p in pets:
        info = [f"- {p.name} (id: {p.id}): {p.species.value}"]
        if p.breed:
            info.append(f"breed={p.breed}")
        if p.weight:
            info.append(f"weight={p.weight}kg")
        if p.birthday:
            info.append(f"birthday={p.birthday.isoformat()}")
        lines.append(", ".join(info))
        if p.profile:
            profile_str = json.dumps(p.profile, ensure_ascii=False)
            lines.append(f"  Profile: {profile_str}")
    return "\n".join(lines)


async def _get_context_messages(
    db: AsyncSession, session_id: uuid.UUID
) -> list[dict]:
    """Load recent messages from the session for LLM context."""
    result = await db.execute(
        select(Chat)
        .where(Chat.session_id == session_id)
        .order_by(Chat.created_at.desc())
        .limit(MAX_CONTEXT_MESSAGES)
    )
    messages = list(reversed(result.scalars().all()))
    return [{"role": m.role.value, "content": m.content} for m in messages]


async def _save_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    role: MessageRole,
    content: str,
    cards_json: str | None = None,
) -> Chat:
    msg = Chat(
        id=uuid.uuid4(),
        session_id=session_id,
        user_id=user_id,
        role=role,
        content=content,
        cards_json=cards_json,
    )
    db.add(msg)
    await db.commit()
    return msg


_SENTINEL = object()


async def _run_chat_agent_to_queue(
    queue: asyncio.Queue,
    request: ChatRequest,
    session: ChatSession,
    user_id: uuid.UUID,
    db: AsyncSession,
    pets: list[Pet],
    context_messages: list[dict],
):
    """Run ChatAgent, pushing SSE events into the queue."""
    pet_context = await _build_pet_context(pets)
    system_msg = CHAT_SYSTEM_PROMPT.format(
        pet_context=pet_context, today_date=date.today().isoformat()
    )

    async def on_token(text):
        await queue.put({"event": "token", "data": json.dumps({"text": text})})

    async def on_card(card_data):
        await queue.put({"event": "card", "data": json.dumps(card_data)})

    try:
        result = await _chat_agent.execute(
            request.message,
            {
                "system_prompt": system_msg,
                "context_messages": context_messages,
                "db": db,
                "user_id": user_id,
                "session_id": session.id,
                "location": request.location,
            },
            on_token=on_token,
            on_card=on_card,
        )
        await queue.put(("_result", result))
    except Exception as e:
        logger.error("chat_agent_error", extra={
            "error_type": type(e).__name__,
            "error_message": str(e)[:500],
        })
        error_text = f"Sorry, I'm having trouble right now. Please try again. (Error: {type(e).__name__})"
        await queue.put({"event": "token", "data": json.dumps({"text": error_text})})
        await queue.put(("_result", {"response": error_text, "cards": []}))
    finally:
        await queue.put(_SENTINEL)


async def _event_generator(
    request: ChatRequest, user_id: uuid.UUID, db: AsyncSession
):
    # 1. Get or create today's session
    session = await _get_or_create_session(db, user_id)
    session_id = str(session.id)

    # 2. Save user message
    await _save_message(db, session.id, user_id, MessageRole.user, request.message)

    # 3. Emergency detection (non-blocking — emitted before chat response)
    if detect_emergency(request.message):
        logger.info("emergency_detected", extra={
            "session_id": session_id,
            "user_id": str(user_id),
        })
        yield {
            "event": "emergency",
            "data": json.dumps({"message": "Possible emergency detected", "action": "find_er"}),
        }

    # 4. Load context
    pets = await _get_pets(db, user_id)
    context_messages = await _get_context_messages(db, session.id)

    # 5. Stream ChatAgent response
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(
        _run_chat_agent_to_queue(
            queue, request, session, user_id, db, pets, context_messages
        )
    )

    result = {"response": "", "cards": []}
    while True:
        item = await queue.get()
        if item is _SENTINEL:
            break
        if isinstance(item, tuple) and item[0] == "_result":
            result = item[1]
            continue
        yield item

    await task
    full_response = result.get("response", "")
    cards = result.get("cards", [])

    # 6. Save assistant response
    cards_json = json.dumps(cards) if cards else None
    await _save_message(
        db, session.id, user_id, MessageRole.assistant, full_response, cards_json
    )

    # 7. Done event
    yield {
        "event": "done",
        "data": json.dumps({"intent": "chat", "session_id": session_id}),
    }


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return EventSourceResponse(_event_generator(request, user_id, db))
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/test_chat_agent.py tests/test_validation.py tests/test_agents_emergency.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/chat.py
git commit -m "refactor: remove intent router, all messages go through unified ChatAgent"
```

---

### Task 6: Delete old agents and update __init__.py

**Files:**
- Delete: `backend/app/agents/router.py`
- Delete: `backend/app/agents/summary_agent.py`
- Delete: `backend/app/agents/map_agent.py`
- Delete: `backend/app/agents/email_agent.py`
- Modify: `backend/app/agents/__init__.py`
- Delete: `backend/tests/test_agents_router.py`
- Delete: `backend/tests/test_summary_agent.py`
- Delete: `backend/tests/test_map_agent.py`
- Delete: `backend/tests/test_email_agent.py`

- [ ] **Step 1: Update __init__.py**

```python
from .base import BaseAgent
from .chat_agent import ChatAgent
from .emergency import detect_emergency
from .tools import TOOL_DEFINITIONS, execute_tool
from .validation import validate_tool_args

__all__ = [
    "BaseAgent",
    "ChatAgent",
    "TOOL_DEFINITIONS",
    "detect_emergency",
    "execute_tool",
    "validate_tool_args",
]
```

- [ ] **Step 2: Verify no other code imports deleted modules**

Run: `grep -r "from app.agents.router\|from app.agents.summary_agent\|from app.agents.map_agent\|from app.agents.email_agent\|import route_intent\|import SummaryAgent\|import MapAgent\|import EmailAgent" backend/app/ --include="*.py" -l`

Expected: Only the files about to be deleted (router.py, summary_agent.py, map_agent.py, email_agent.py, __init__.py which was already updated). If `main.py` or any other file shows up, fix its imports first.

- [ ] **Step 3: Delete old agent files**

```bash
cd backend
rm app/agents/router.py app/agents/summary_agent.py app/agents/map_agent.py app/agents/email_agent.py
rm tests/test_agents_router.py tests/test_summary_agent.py tests/test_map_agent.py tests/test_email_agent.py
```

- [ ] **Step 4: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A backend/app/agents/ backend/tests/
git commit -m "refactor: delete router, summary, map, email agents — unified ChatAgent handles all"
```
