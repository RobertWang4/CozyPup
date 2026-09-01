import uuid
from types import SimpleNamespace

import pytest

from app.agents.emergency import EmergencyCheckResult
from app.agents.pre_processing.types import SuggestedAction
from app.memory import MemorySnippet, RetrievedContext


def test_build_preprocessor_hints_matches_chat_policy_for_first_multi_action_turn():
    from app.agents.chat_turn import build_preprocessor_hints

    hints = build_preprocessor_hints(
        [
            SuggestedAction(
                tool_name="create_calendar_event",
                arguments={"title": "维尼吐了"},
                confidence=0.9,
            ),
            SuggestedAction(
                tool_name="create_reminder",
                arguments={"title": "明天打疫苗"},
                confidence=0.8,
            ),
            SuggestedAction(
                tool_name="update_pet_profile",
                arguments={"weight": 4.5},
                confidence=0.4,
            ),
        ],
        is_first_message=True,
        lang="zh",
    )

    assert 'create_calendar_event({"title": "维尼吐了"})' in hints
    assert 'create_reminder({"title": "明天打疫苗"})' in hints
    assert not any("weight" in hint for hint in hints)
    assert any("introduce_product()" in hint for hint in hints)
    assert any("多个事件/提醒意图" in hint for hint in hints)


def test_select_chat_model_keeps_emergency_routing_policy():
    from app.agents.chat_turn import select_chat_model

    assert select_chat_model(
        is_emergency=False,
        default_model="daily-model",
        emergency_model="urgent-model",
    ) == "daily-model"
    assert select_chat_model(
        is_emergency=True,
        default_model="daily-model",
        emergency_model="urgent-model",
    ) == "urgent-model"


def test_context_messages_and_recent_user_images_match_router_behavior():
    from app.agents.chat_turn import build_context_messages, recent_user_image_urls

    user_role = SimpleNamespace(value="user")
    assistant_role = SimpleNamespace(value="assistant")
    rows = [
        SimpleNamespace(role=user_role, content="第一张照片", image_urls=["/old.jpg"]),
        SimpleNamespace(role=assistant_role, content="看到了", image_urls=[]),
        SimpleNamespace(role=user_role, content="新的照片", image_urls=["/new.jpg"]),
    ]

    context_messages = build_context_messages(rows)

    assert context_messages[0]["content"] == "第一张照片\n[附带了1张图片，如需查看可调用 request_images]"
    assert context_messages[1] == {"role": "assistant", "content": "看到了"}
    assert recent_user_image_urls(rows) == ["/new.jpg"]


@pytest.mark.asyncio
async def test_build_agent_prompt_input_collects_prompt_memory_messages_and_images():
    from app.agents.chat_turn import build_agent_prompt_input

    async def fake_retrieve(**kwargs):
        return RetrievedContext(
            behavioral_memories=[
                MemorySnippet(kind="behavioral", content="维尼上周吐过一次")
            ]
        )

    bundle = await build_agent_prompt_input(
        message="维尼又吐了",
        db=object(),
        user_id=uuid.uuid4(),
        pets=[],
        session_summary=None,
        context_messages=[
            SimpleNamespace(
                role=SimpleNamespace(value="user"),
                content="之前发过照片",
                image_urls=["/photo.jpg"],
            )
        ],
        emergency_result=EmergencyCheckResult(detected=False, keywords=[]),
        suggested_actions=[
            SuggestedAction(
                tool_name="create_calendar_event",
                arguments={"title": "维尼吐了"},
                confidence=0.9,
            )
        ],
        lang="zh",
        image_count=2,
        retrieve_memory_context=fake_retrieve,
        default_model="daily-model",
        emergency_model="urgent-model",
        today="2026-06-14",
    )

    assert bundle.model == "daily-model"
    assert bundle.today == "2026-06-14"
    assert "维尼上周吐过一次" in bundle.memory_context
    assert "维尼上周吐过一次" in bundle.system_prompt
    assert bundle.messages[-1]["content"] == "维尼又吐了\n[用户附带了2张图片]"
    assert bundle.recent_image_urls == ["/photo.jpg"]
