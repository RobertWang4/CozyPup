"""LLM judge for text-quality rubrics that deterministic graders can't check."""

from __future__ import annotations

import json

import litellm

from .client import ChatResult, get_tools_executed
from .scenario import HarnessScenario

SYSTEM_PROMPT = (
    "You grade a pet-care assistant's reply against rubric statements.\n"
    "For each rubric decide whether the reply satisfies it. Judge only what the "
    "rubric asks about; ignore style you were not asked about.\n"
    "Product context: when a write succeeds the app shows a card (record / pet_updated / "
    "reminder_created etc.) and the assistant text is often just a short opener like "
    "'正在记录…' or 'Recording…' — the card, not the text, is the confirmation. Treat a shown "
    "card plus an executed tool as a completed action. A confirm_action card means the action "
    "has NOT happened yet and the reply must not claim it did.\n"
    'Answer with JSON: {"verdicts": [{"rubric": "<rubric text>", "pass": true|false, '
    '"reason": "<one short sentence>"}]} — one entry per rubric, in order.'
)


def _build_prompt(scenario: HarnessScenario, result: ChatResult, rubrics: list[str]) -> str:
    card_types = [str(card.get("type")) for card in result.cards]
    parts = [
        "USER MESSAGES:",
        *(f"- {message}" for message in scenario.messages),
        "",
        "ASSISTANT REPLY:",
        result.text or "(empty)",
        "",
        f"CARDS SHOWN: {', '.join(card_types) or '(none)'}",
        f"TOOLS EXECUTED: {', '.join(get_tools_executed(result)) or '(none)'}",
        "",
        "RUBRICS:",
        *(f"{index}. {rubric}" for index, rubric in enumerate(rubrics, 1)),
    ]
    return "\n".join(parts)


async def judge_result(scenario: HarnessScenario, result: ChatResult) -> list[str]:
    """Return one failure reason per rubric the reply did not satisfy."""
    rubrics = list(scenario.expect.judge)
    if not rubrics:
        return []

    from app.agents import llm_extra_kwargs
    from app.config import settings

    try:
        response = await litellm.acompletion(
            model=settings.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(scenario, result, rubrics)},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            **llm_extra_kwargs(),
        )
        data = json.loads(response.choices[0].message.content)
    except Exception as exc:
        return [f"judge error: {type(exc).__name__}: {exc}"]

    reasons: list[str] = []
    for verdict in data.get("verdicts") or []:
        if not isinstance(verdict, dict) or verdict.get("pass") is True:
            continue
        rubric = verdict.get("rubric") or "(unknown rubric)"
        reason = verdict.get("reason") or "no reason given"
        reasons.append(f"judge: {rubric} — {reason}")
    return reasons
