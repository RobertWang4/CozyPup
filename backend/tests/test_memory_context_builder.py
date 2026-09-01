import asyncio
import time
import uuid
from types import SimpleNamespace

import pytest

from app.agents.prompts_v2 import build_system_prompt
from app.memory import MemorySnippet, RetrievedContext
from app.memory.context_builder import build_memory_context


@pytest.mark.asyncio
async def test_build_memory_context_uses_single_pet_hint():
    calls = []
    pet_id = uuid.uuid4()
    user_id = uuid.uuid4()
    pet = SimpleNamespace(id=pet_id, species="dog")

    async def fake_retrieve(**kwargs):
        calls.append(kwargs)
        return RetrievedContext(
            behavioral_memories=[MemorySnippet(kind="behavioral", content="维尼上周吐了")]
        )

    context = await build_memory_context(
        message="维尼又吐了怎么办",
        db=object(),
        user_id=user_id,
        pets=[pet],
        retrieve=fake_retrieve,
    )

    assert context.behavioral_memories[0].content == "维尼上周吐了"
    assert calls[0]["pet_id"] == pet_id
    assert calls[0]["species"] == "dog"
    assert calls[0]["user_id"] == user_id


@pytest.mark.asyncio
async def test_build_memory_context_returns_empty_without_runtime_inputs():
    called = False

    async def fake_retrieve(**kwargs):
        nonlocal called
        called = True
        return RetrievedContext()

    context = await build_memory_context(
        message="",
        db=object(),
        user_id=uuid.uuid4(),
        retrieve=fake_retrieve,
    )

    assert context == RetrievedContext()
    assert called is False


@pytest.mark.asyncio
async def test_build_memory_context_times_out_without_blocking_chat():
    async def slow_retrieve(**kwargs):
        await asyncio.sleep(1)
        return RetrievedContext(
            behavioral_memories=[MemorySnippet(kind="behavioral", content="should not block")]
        )

    started = time.perf_counter()
    context = await build_memory_context(
        message="维尼又吐了怎么办",
        db=object(),
        user_id=uuid.uuid4(),
        retrieve=slow_retrieve,
        timeout_ms=25,
    )

    assert context == RetrievedContext()
    assert time.perf_counter() - started < 0.2


def test_system_prompt_includes_memory_context_before_dynamic_hints():
    prompt = build_system_prompt(
        pets=[],
        today="2026-06-13",
        memory_context="## Relevant Pet/User Memory\n- 维尼上周吐了",
        preprocessor_hints=["UNIQUE_DYNAMIC_HINT"],
    )

    assert "## Relevant Pet/User Memory" in prompt
    assert prompt.index("## Relevant Pet/User Memory") < prompt.index("UNIQUE_DYNAMIC_HINT")
