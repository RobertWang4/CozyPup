import inspect
import uuid
from types import SimpleNamespace

from app.agents import chat_finalizer
from app.routers import chat


def test_chat_turn_memory_source_id_is_assistant_message_id():
    session_id = uuid.uuid4()
    assistant_message = SimpleNamespace(id=uuid.uuid4(), session_id=session_id)

    assert chat._chat_turn_memory_source_id(assistant_message) == assistant_message.id


def test_chat_turn_memory_write_does_not_use_session_id_source():
    memory_block = inspect.getsource(chat_finalizer.finalize_assistant_turn)

    assert "source_id=session.id" not in memory_block
    assert "source_id=source_id" in memory_block
