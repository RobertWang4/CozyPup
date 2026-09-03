import json
from types import SimpleNamespace

import pytest

from app.agent_harness import judge as judge_module
from app.agent_harness.client import ChatResult
from app.agent_harness.judge import judge_result
from app.agent_harness.scenario import ExpectedOutcome, HarnessScenario


def _scenario(rubrics):
    return HarnessScenario(
        id="judged",
        description="",
        messages=["把豆豆今天的呕吐记录删掉"],
        expect=ExpectedOutcome(judge=rubrics),
    )


def _result():
    return ChatResult(
        text="已经帮你删掉了",
        cards=[{"type": "confirm_action"}],
        trace={"events": [{
            "type": "run_completed",
            "data": {"tools_executed": ["delete_calendar_event"]},
        }]},
    )


def _fake_litellm(payload, captured=None):
    async def acompletion(**kwargs):
        if captured is not None:
            captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )

    return SimpleNamespace(acompletion=acompletion)


@pytest.mark.asyncio
async def test_judge_returns_no_reasons_when_all_rubrics_pass(monkeypatch):
    monkeypatch.setattr(judge_module, "litellm", _fake_litellm(
        {"verdicts": [{"rubric": "asks for confirmation", "pass": True, "reason": "it does"}]}
    ))

    assert await judge_result(_scenario(["asks for confirmation"]), _result()) == []


@pytest.mark.asyncio
async def test_judge_reports_failed_rubrics_and_sends_context(monkeypatch):
    captured = {}
    monkeypatch.setattr(judge_module, "litellm", _fake_litellm(
        {"verdicts": [
            {"rubric": "must not claim deletion", "pass": False, "reason": "it says 已经删掉了"},
            {"rubric": "asks for confirmation", "pass": True, "reason": "ok"},
        ]},
        captured,
    ))

    reasons = await judge_result(
        _scenario(["must not claim deletion", "asks for confirmation"]), _result()
    )

    assert reasons == ["judge: must not claim deletion — it says 已经删掉了"]
    assert captured["temperature"] == 0
    assert captured["response_format"] == {"type": "json_object"}
    prompt = captured["messages"][1]["content"]
    assert "把豆豆今天的呕吐记录删掉" in prompt
    assert "已经帮你删掉了" in prompt
    assert "confirm_action" in prompt
    assert "delete_calendar_event" in prompt


@pytest.mark.asyncio
async def test_judge_skips_call_without_rubrics(monkeypatch):
    def boom(**kwargs):
        raise AssertionError("should not call the model")

    monkeypatch.setattr(judge_module, "litellm", SimpleNamespace(acompletion=boom))

    assert await judge_result(_scenario([]), _result()) == []


@pytest.mark.asyncio
async def test_judge_errors_do_not_crash_the_run(monkeypatch):
    async def acompletion(**kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr(judge_module, "litellm", SimpleNamespace(acompletion=acompletion))

    reasons = await judge_result(_scenario(["anything"]), _result())

    assert len(reasons) == 1
    assert reasons[0].startswith("judge error: RuntimeError: model down")


@pytest.mark.asyncio
async def test_judge_handles_malformed_json(monkeypatch):
    async def acompletion(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
        )

    monkeypatch.setattr(judge_module, "litellm", SimpleNamespace(acompletion=acompletion))

    reasons = await judge_result(_scenario(["anything"]), _result())

    assert reasons[0].startswith("judge error: JSONDecodeError")
