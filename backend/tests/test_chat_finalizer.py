import json
import uuid
from types import SimpleNamespace

import pytest

from app.agents.pre_processing.types import SuggestedAction


def test_chat_turn_memory_source_id_uses_assistant_message_id():
    from app.agents.chat_finalizer import chat_turn_memory_source_id

    assistant_message = SimpleNamespace(id=uuid.uuid4(), session_id=uuid.uuid4())

    assert chat_turn_memory_source_id(assistant_message) == assistant_message.id


def test_should_run_final_fallback_only_for_critical_missed_no_tool_turns():
    from app.agents.chat_finalizer import should_run_final_fallback

    empty_result = SimpleNamespace(cards=[], confirm_cards=[], tools_called=set())
    critical_action = SuggestedAction(
        tool_name="search_places",
        arguments={"query": "vet"},
        confidence=0.9,
    )
    advisory_action = SuggestedAction(
        tool_name="create_calendar_event",
        arguments={"title": "walk"},
        confidence=0.9,
    )

    assert should_run_final_fallback(empty_result, [critical_action]) is True
    assert should_run_final_fallback(empty_result, [advisory_action]) is False
    assert should_run_final_fallback(
        SimpleNamespace(cards=[], confirm_cards=[], tools_called={"search_places"}),
        [critical_action],
    ) is False


def test_assistant_cards_json_combines_normal_and_confirm_cards():
    from app.agents.chat_finalizer import assistant_cards_json

    result = SimpleNamespace(
        cards=[{"type": "record"}],
        confirm_cards=[{"type": "confirm_action", "action_id": "a1"}],
    )

    all_cards, cards_json = assistant_cards_json(result)

    assert all_cards == [
        {"type": "record"},
        {"type": "confirm_action", "action_id": "a1"},
    ]
    assert json.loads(cards_json) == all_cards


def test_chat_turn_memory_content_truncates_assistant_text():
    from app.agents.chat_finalizer import chat_turn_memory_content

    content = chat_turn_memory_content("用户输入", "a" * 600)

    assert content == f"用户: 用户输入\n助手: {'a' * 500}"


@pytest.mark.asyncio
async def test_finalize_assistant_turn_saves_message_and_tracks_memory_and_summary():
    from app.agents.chat_finalizer import finalize_assistant_turn

    class FakeSessionFactory:
        def __init__(self, label):
            self.label = label

        async def __aenter__(self):
            return self.label

        async def __aexit__(self, exc_type, exc, tb):
            return False

    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    assistant_id = uuid.uuid4()
    result = SimpleNamespace(
        response_text="助手回复",
        cards=[{"type": "record"}],
        confirm_cards=[],
    )
    save_calls = []
    memory_calls = []
    summary_calls = []
    tracked = []

    async def save_message(db, saved_session_id, saved_user_id, role, content, cards_json):
        save_calls.append((db, saved_session_id, saved_user_id, role, content, cards_json))
        return SimpleNamespace(id=assistant_id)

    async def upsert_memory(**kwargs):
        memory_calls.append(kwargs)

    async def trigger_summary(saved_session_id, bg_db, *, lang):
        summary_calls.append((saved_session_id, bg_db, lang))

    def track_task(coro):
        tracked.append(coro)

    finalization = await finalize_assistant_turn(
        db="request-db",
        session_id=session_id,
        user_id=user_id,
        assistant_role="assistant",
        result=result,
        user_message="用户输入",
        lang="zh",
        save_message=save_message,
        async_session_factory=lambda: FakeSessionFactory("bg-db"),
        track_task=track_task,
        upsert_memory=upsert_memory,
        trigger_summary=trigger_summary,
    )

    assert finalization.all_cards == [{"type": "record"}]
    assert finalization.assistant_message.id == assistant_id
    assert save_calls == [
        (
            "request-db",
            session_id,
            user_id,
            "assistant",
            "助手回复",
            json.dumps([{"type": "record"}]),
        )
    ]

    assert len(tracked) == 2
    for coro in tracked:
        await coro

    assert memory_calls == [{
        "db": "bg-db",
        "user_id": user_id,
        "source_kind": "chat_turn",
        "source_id": assistant_id,
        "content": "用户: 用户输入\n助手: 助手回复",
    }]
    assert summary_calls == [(session_id, "bg-db", "zh")]


@pytest.mark.asyncio
async def test_apply_profile_extraction_merges_matching_pet_and_commits():
    from app.agents.chat_finalizer import apply_profile_extraction

    class FakeDb:
        def __init__(self):
            self.commits = 0

        async def commit(self):
            self.commits += 1

    pet_id = uuid.uuid4()
    pet = SimpleNamespace(id=pet_id, name="维尼", profile_md="# old")
    merge_calls = []

    async def extraction_task():
        return {"pet_id": str(pet_id), "info": {"breed": "可卡布", "gender": "公"}}

    async def merge_profile(target_pet, info, *, lang):
        merge_calls.append((target_pet, info, lang))
        return "# new profile"

    db = FakeDb()

    changed = await apply_profile_extraction(
        extractor_task=extraction_task(),
        pets=[pet],
        db=db,
        lang="zh",
        merge_profile=merge_profile,
    )

    assert changed is True
    assert pet.profile_md == "# new profile"
    assert db.commits == 1
    assert merge_calls == [
        (pet, {"breed": "可卡布", "gender": "公"}, "zh"),
    ]


def test_record_chat_audit_builds_legal_audit_payload():
    from app.agents.chat_finalizer import record_chat_audit

    user_id = uuid.uuid4()
    pet_id = uuid.uuid4()
    pet = SimpleNamespace(id=pet_id, species=SimpleNamespace(value="dog"))
    calls = []

    def log_chat_turn(**kwargs):
        calls.append(kwargs)

    ok = record_chat_audit(
        user_id=user_id,
        pets=[pet],
        raw_query="维尼吐了",
        is_emergency_route=False,
        all_cards=[{"type": "references"}],
        llm_output="先观察精神和食欲。",
        response_time_ms=123,
        model_used="grok-4-1-fast",
        session_id="session-1",
        lang="zh",
        tools_called={"search_knowledge", "query_calendar_events"},
        keyword_emergency=True,
        client_version="1.2.3",
        log_chat_turn=log_chat_turn,
        extract_retrieved_chunks=lambda cards: [{"title": "Vomiting", "url": "https://example.com"}],
        get_correlation_id=lambda: "cid-1",
    )

    assert ok is True
    assert calls == [{
        "user_id": user_id,
        "pet_id": pet_id,
        "species": "dog",
        "raw_query": "维尼吐了",
        "is_emergency_route": False,
        "retrieved_chunks": [{"title": "Vomiting", "url": "https://example.com"}],
        "llm_output": "先观察精神和食欲。",
        "response_time_ms": 123,
        "model_used": "grok-4-1-fast",
        "metadata_json": {
            "session_id": "session-1",
            "lang": "zh",
            "tools_called": ["query_calendar_events", "search_knowledge"],
            "keyword_emergency": True,
            "correlation_id": "cid-1",
            "client_version": "1.2.3",
        },
    }]


def test_record_chat_audit_swallows_audit_hook_errors():
    from app.agents.chat_finalizer import record_chat_audit

    def failing_log_chat_turn(**kwargs):
        raise RuntimeError("audit backend down")

    ok = record_chat_audit(
        user_id=uuid.uuid4(),
        pets=[],
        raw_query="hello",
        is_emergency_route=True,
        all_cards=[],
        llm_output="route now",
        response_time_ms=20,
        model_used=None,
        session_id="session-1",
        lang="en",
        tools_called=set(),
        keyword_emergency=True,
        client_version=None,
        metadata_extra={"short_circuit": True, "category": "toxin"},
        log_chat_turn=failing_log_chat_turn,
        extract_retrieved_chunks=lambda cards: [],
        get_correlation_id=lambda: "cid-2",
    )

    assert ok is False
