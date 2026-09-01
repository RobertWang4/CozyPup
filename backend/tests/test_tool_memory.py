from unittest.mock import Mock

from app.agents.tool_invocation import ToolInvocation
from app.agents.tool_memory import sync_tool_memory


def test_calendar_create_schedules_memory_upsert():
    schedule_upsert = Mock()
    schedule_delete = Mock()

    sync_tool_memory(
        ToolInvocation(id="call-1", name="create_calendar_event", arguments={}),
        {"success": True, "event_id": "event-1"},
        schedule_upsert=schedule_upsert,
        schedule_delete=schedule_delete,
    )

    schedule_upsert.assert_called_once_with("event-1")
    schedule_delete.assert_not_called()


def test_calendar_update_schedules_memory_upsert():
    schedule_upsert = Mock()

    sync_tool_memory(
        ToolInvocation(id="call-1", name="update_calendar_event", arguments={}),
        {"success": True, "event_id": "event-1"},
        schedule_upsert=schedule_upsert,
        schedule_delete=Mock(),
    )

    schedule_upsert.assert_called_once_with("event-1")


def test_calendar_delete_schedules_memory_delete():
    schedule_delete = Mock()

    sync_tool_memory(
        ToolInvocation(id="call-1", name="delete_calendar_event", arguments={}),
        {"success": True, "event_id": "event-1"},
        schedule_upsert=Mock(),
        schedule_delete=schedule_delete,
    )

    schedule_delete.assert_called_once_with("event-1")


def test_failed_or_non_event_tool_does_not_sync_memory():
    schedule_upsert = Mock()
    schedule_delete = Mock()

    sync_tool_memory(
        ToolInvocation(id="call-1", name="create_pet", arguments={}),
        {"success": True, "pet_id": "pet-1"},
        schedule_upsert=schedule_upsert,
        schedule_delete=schedule_delete,
    )
    sync_tool_memory(
        ToolInvocation(id="call-2", name="create_calendar_event", arguments={}),
        {"success": False, "event_id": "event-1"},
        schedule_upsert=schedule_upsert,
        schedule_delete=schedule_delete,
    )

    schedule_upsert.assert_not_called()
    schedule_delete.assert_not_called()
