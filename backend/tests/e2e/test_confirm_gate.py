"""E2E tests for the confirm-gate policy.

Verifies mechanical verb-bypass: every mutating tool pops a confirm_action card
by default, UNLESS the user's message matches the global or tool-specific verb
regex in app.agents.constants.

Test logic:
  - Only asserts when LLM actually called a mutating tool; skips when LLM
    chose not to mutate (that's a separate routing concern).
  - Uses debug fixture to inspect tools_called from trace.
"""

from __future__ import annotations

import pytest

from .conftest import E2EClient
from app.agents.constants import (
    MUTATING_TOOLS_WITH_VERB_BYPASS,
    CONFIRM_TOOLS,
    CONDITIONAL_CONFIRM_ACTIONS,
)


def _tools_called(result) -> list[str]:
    """Extract tools_called from debug trace."""
    if not result.trace:
        return []
    for step in reversed(result.trace.get("steps", [])):
        data = step.get("data", {})
        if isinstance(data, dict) and "tools_called" in data:
            return data.get("tools_called") or []
    return []


def _any_mutating_called(result) -> tuple[bool, list[str]]:
    """Returns (any_mutating, list_of_called_tools)."""
    called = _tools_called(result)
    mutating = [t for t in called if t in MUTATING_TOOLS_WITH_VERB_BYPASS or t in CONFIRM_TOOLS]
    return bool(mutating), called


# (message, expect_confirm_when_mutation_fires)
CASES: list[tuple[str, bool, str]] = [
    # --- implicit (should confirm) ---
    ("小维今天去公园玩了",                    True,  "implicit: state of fact"),
    ("小维是可卡布犬",                        True,  "implicit: breed claim"),
    ("我朋友家还有一只叫 Timmy 的狗",         True,  "implicit: mentioning another pet"),
    ("小维下周要打疫苗",                      True,  "implicit: future fact"),
    ("我每天都会给小维遛狗",                  True,  "implicit: habit"),
    ("兽医最近不太靠谱",                      True,  "implicit: complaint"),
    ("我英文不太好",                          True,  "implicit: statement"),

    # --- explicit (should bypass) ---
    ("帮我记下小维今天遛狗了",                False, "explicit: 记下"),
    ("把小维的品种改成可卡布",                False, "explicit: 改成"),
    ("我新养了一只叫 Timmy 的狗",             False, "explicit: 新养"),
    ("提醒我下周给小维打疫苗",                False, "explicit: 提醒我 (global)"),
    ("帮我加个每天遛狗的日常任务",            False, "explicit: 加...日常"),
    ("帮我写一封邮件给兽医问一下用药",         False, "explicit: 写邮件"),
    ("切换成英文",                            False, "explicit: 切换成"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("message,expect_confirm,reason", CASES)
async def test_confirm_gate(e2e_debug_with_pet: E2EClient, message: str, expect_confirm: bool, reason: str):
    # Create pet named 小维 so messages resolve
    result = await e2e_debug_with_pet.chat(message)
    assert result.error is None, f"[{reason}] chat error: {result.error}"

    mutated, called = _any_mutating_called(result)
    if not mutated:
        pytest.skip(f"[{reason}] LLM called no mutating tool (called={called}); "
                    f"can't test gate. msg={message}")

    has_confirm = result.has_card("confirm_action")

    if expect_confirm:
        assert has_confirm, (
            f"[{reason}] expected confirm_action but got none. "
            f"tools_called={called}\n{result.dump()}"
        )
    else:
        assert not has_confirm, (
            f"[{reason}] expected direct execution but got confirm_action. "
            f"tools_called={called}\n{result.dump()}"
        )


# === Always-confirm tools (CONFIRM_TOOLS) — no bypass even with explicit verb ===

@pytest.mark.asyncio
async def test_delete_pet_always_confirms(e2e_debug_with_pet: E2EClient):
    """delete_pet must pop confirm even with explicit verb."""
    result = await e2e_debug_with_pet.chat("请立即永久删除小维的档案")
    assert result.error is None

    called = _tools_called(result)
    if "delete_pet" not in called:
        pytest.skip(f"LLM didn't call delete_pet (called={called})")

    assert result.has_card("confirm_action"), (
        f"delete_pet executed without confirm!\n{result.dump()}"
    )


@pytest.mark.asyncio
async def test_delete_event_always_confirms(e2e_debug_with_pet: E2EClient):
    """delete_calendar_event must pop confirm even with explicit 'delete' verb."""
    # Setup: create an event
    await e2e_debug_with_pet.chat("帮我记下小维今天遛狗了")
    # Retry once on flaky SSE connection
    result = await e2e_debug_with_pet.chat("删掉刚才那条遛狗记录")
    if result.error:
        result = await e2e_debug_with_pet.chat("删掉刚才那条遛狗记录")
    assert result.error is None, f"chat error after retry: {result.error}"

    called = _tools_called(result)
    if "delete_calendar_event" not in called:
        pytest.skip(f"LLM didn't call delete_calendar_event (called={called})")

    assert result.has_card("confirm_action"), (
        f"delete_calendar_event executed without confirm!\n{result.dump()}"
    )


# === Unit-level verification: needs_confirm policy correctness ===
# This complements E2E tests with direct function-level checks that don't
# depend on LLM tool-choice.

def test_policy_always_confirm_tools():
    """CONFIRM_TOOLS always return True, regardless of user text."""
    from app.agents.constants import needs_confirm
    for tool in CONFIRM_TOOLS:
        assert needs_confirm(tool, {}, "随便什么文字都不能 bypass"), \
            f"{tool} should always confirm"
        assert needs_confirm(tool, {}, "记一下 保存 删除"), \
            f"{tool} should confirm even with explicit verbs"


def test_policy_conditional_confirm():
    """manage_daily_task destructive actions always confirm."""
    from app.agents.constants import needs_confirm
    for action in CONDITIONAL_CONFIRM_ACTIONS["manage_daily_task"]:
        assert needs_confirm("manage_daily_task", {"action": action}, "explicit记下"), \
            f"action={action} should always confirm"


def test_policy_verb_bypass():
    """Mutating tools bypass confirm on explicit verbs."""
    from app.agents.constants import needs_confirm
    # Global verb: remind me should bypass for any mutating tool
    for tool in MUTATING_TOOLS_WITH_VERB_BYPASS:
        assert not needs_confirm(tool, {}, "提醒我下周做某事"), \
            f"{tool} should bypass on 提醒我"
    # No verb: implicit fact should confirm for any mutating tool
    for tool in MUTATING_TOOLS_WITH_VERB_BYPASS:
        if tool == "manage_daily_task":
            continue  # special-cased
        assert needs_confirm(tool, {}, "他是可卡布"), \
            f"{tool} should confirm on implicit statement"
