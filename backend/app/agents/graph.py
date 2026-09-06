"""LangGraph version of the unified agent loop.

Same behavior as the hand-written `while` loop in orchestrator.py — the nodes
call the orchestrator's existing helpers rather than reimplementing them:

    prepare   → seed messages + pushback preamble
    model     → micro_compact + vision switch + _stream_completion
    tools     → dispatch_tool per tool_call (+ image injection, skip_round2);
                calls needing user confirmation are deferred, not executed
    confirm   → interrupt() on one deferred call; on resume execute it
    review    → plan nag → write-claim nag → nudge
    finalize  → text assembly, fabrication guard, empty-reply fallback

Edges (MAX_ROUNDS is checked on both back-edges, round increments in `model`):

    START → prepare → model
    model → tools (tool_calls) | review (no tool_calls)
    tools → confirm (deferred) | finalize (skip_round2 or round cap) | model
    confirm → confirm (more deferred) | model (tool errored) | finalize
    review → model (retry, round cap) | finalize
    finalize → END

Streaming: token / thinking / card events are pushed from inside the nodes via
`get_stream_writer()` as {"event": ..., "data": ...} dicts. `stream_agent()`
below is the entry point used by `AgentEngine` and by `run_orchestrator`.

Non-serializable per-request context (db, trace, model names, ids) travels in
`config["configurable"]`; conversation state travels in `AgentState`.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from operator import add
from typing import Annotated, Any, AsyncIterator, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents.locale import t
from app.agents.micro_compact import micro_compact
from app.agents.orchestrator import (
    MAX_ROUNDS,
    OrchestratorResult,
    _can_skip_round2,
    _detect_pushback,
    _find_missed_tools,
    _inject_nudge,
    _inject_pushback_preamble,
    _inject_write_claim_nag,
    _stream_completion,
    _text_claims_write,
    _WRITE_TOOLS,
    dispatch_tool,
)
from app.agents.tool_context import ToolDispatchContext
from app.agents.tool_execution import handle_tool_execution
from app.agents.tool_invocation import ToolInvocation
from app.agents.trace_collector import INACTIVE_TRACE
from app.debug.correlation import get_correlation_id
from app.config import settings

logger = logging.getLogger(__name__)


def _union(a: set, b: set) -> set:
    return a | b


class AgentState(TypedDict, total=False):
    # Conversation
    system_prompt: str
    context_messages: list[dict]
    messages: Annotated[list[dict], add]   # append-only; nodes return their delta
    round: int
    # Last round's model output (consumed by tools / review)
    round_text: str
    tool_calls: list[dict]
    # Loop control
    nudge_used: bool
    plan_nag_used: bool
    write_claim_nag_used: bool
    plan_steps: list[dict]
    retry: bool
    skip_round2: bool
    # Confirm gate: calls parked for `interrupt()`, consumed one at a time
    deferred_confirms: list[dict]
    resumed: bool
    confirm_error: bool
    confirm_success: bool
    confirm_reentrant: bool
    # Results
    text_parts: Annotated[list[str], add]
    cards: Annotated[list[dict], add]
    confirm_cards: Annotated[list[dict], add]
    tools_called: Annotated[set[str], _union]
    tools_executed: Annotated[set[str], _union]
    prompt_tokens: Annotated[int, add]
    completion_tokens: Annotated[int, add]
    response_text: str
    # Request context (read-only)
    lang: str
    session_id: str
    today: str
    pets: list[dict] | None
    location: dict | None
    image_urls: list[str] | None
    recent_image_urls: list[str] | None
    suggested_actions: list[dict]


# ---------------------------------------------------------------------------
# Stream helpers — nodes push SSE payloads; chat.py serializes them
# ---------------------------------------------------------------------------

def _emit(event: str, data: dict) -> None:
    get_stream_writer()({"event": event, "data": data})


def _emit_token(text: str) -> None:
    _emit("token", {"text": text})


def _emit_thinking(text: str, tool_name: str) -> None:
    _emit("thinking", {"text": text, "tool": tool_name})


def _emit_card(card: dict) -> None:
    _emit("card", card)


def _latest_user_has_images(messages: list[dict]) -> bool:
    """True if the last user message contains image_url content parts."""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, list):
                return any(
                    part.get("type") == "image_url"
                    for part in content
                    if isinstance(part, dict)
                )
            return False
    return False


def _pet_to_dict(pet: Any) -> dict:
    """Flatten an ORM Pet into the plain dict the graph carries in state.

    Downstream of the graph only `id` / `name` / `species` are read
    (tool_guards, describe_tool_call, lookup_event_info) — the system prompt
    is still built from the ORM objects before the graph starts.
    """
    if isinstance(pet, dict):
        return pet
    species = getattr(pet, "species", None)
    return {
        "id": str(getattr(pet, "id", "")),
        "name": getattr(pet, "name", "") or "",
        "species": str(getattr(species, "value", species) or ""),
    }


def _action_to_dict(action: Any) -> dict:
    """Flatten a SuggestedAction into the plain dict `review` reads."""
    if isinstance(action, dict):
        return action
    return {
        "tool_name": action.tool_name,
        "arguments": action.arguments,
        "confidence": action.confidence,
    }


def _round_result(state: AgentState) -> OrchestratorResult:
    """Seed an OrchestratorResult for `dispatch_tool` from the graph state.

    cards/confirm_cards start empty so whatever the round appends is exactly
    the delta the reducers need; the accumulating sets/lists are seeded so
    `_can_skip_round2` and the guards see the full run so far.
    """
    return OrchestratorResult(
        tools_called=set(state.get("tools_called") or set()),
        tools_executed=set(state.get("tools_executed") or set()),
        plan_steps=list(state.get("plan_steps") or []),
    )


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def prepare_node(state: AgentState) -> dict:
    lang = state["lang"]
    messages = [{"role": "system", "content": state["system_prompt"]}]
    messages.extend(state.get("context_messages") or [])

    # Pushback defense: if the user's latest turn disputes a prior completion
    # claim, inject a high-priority system note so the LLM ignores its own
    # fabricated chat history and re-verifies against the DB.
    latest_user_text = ""
    for m in reversed(state.get("context_messages") or []):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                latest_user_text = c
            elif isinstance(c, list):
                latest_user_text = " ".join(
                    part.get("text", "") for part in c if isinstance(part, dict)
                )
            break
    if _detect_pushback(latest_user_text, lang):
        _inject_pushback_preamble(messages, lang)
        logger.info("pushback_preamble_injected", extra={
            "user_text_sample": latest_user_text[:120],
        })

    return {"messages": messages}


async def model_node(state: AgentState, config: RunnableConfig) -> dict:
    from app.debug.trace_logger import trace_log, messages_for_trace

    cfg = config["configurable"]
    trace = cfg["trace"]
    lang = state["lang"]
    use_model = cfg["model"]
    round_num = state["round"]

    # Compress older tool_result payloads to save prompt tokens — keep
    # only the most recent round's full results. `messages` in state is
    # append-only, so compaction runs on a local copy; the bytes the LLM
    # sees are identical to compacting in place, because micro_compact
    # re-derives each summary from the original content and skips anything
    # already under 200 chars.
    messages = state["messages"]
    if round_num > 0:
        messages = [dict(m) for m in messages]
        micro_compact(messages)

    # Switch to vision model when images are in the last user message
    is_vision = _latest_user_has_images(messages)
    round_model = cfg["vision_model"] if is_vision else use_model

    trace.record_event("model_started", {
        "round": round_num,
        "model": round_model,
        "is_vision": is_vision,
    })

    round_text, tool_calls, usage = await _stream_completion(
        messages, round_model, _emit_token, on_thinking=_emit_thinking, lang=lang,
        trace=trace, round_num=round_num, is_vision=is_vision,
    )

    trace.record_event("model_completed", {
        "round": round_num,
        "model": round_model,
        "tool_calls": [tc["function"]["name"] for tc in tool_calls],
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
    })

    # Log LLM request
    trace_log("llm_request", round=round_num, data={
        "model": use_model,
        "message_count": len(messages),
        "messages_preview": [
            {"role": m["role"], "content": (m.get("content") or "")[:200]}
            for m in messages[-3:]
        ],
        # Full prompt (system + history + user) on round 0 so a trace can be
        # replayed offline; later rounds only append tool results, which
        # tool_result entries already carry in full.
        **({"messages": messages_for_trace(messages)} if round_num == 0 else {}),
    })

    # Log LLM response
    trace_log("llm_response", round=round_num, data={
        "model": use_model,
        "text_length": len(round_text),
        "text_preview": round_text[:300] if round_text else "",
        "content": round_text or "",     # NEW — full content for admin trace
        "tool_calls": [
            {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}
            for tc in tool_calls
        ] if tool_calls else [],
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0),
    })

    return {
        "round": round_num + 1,
        "round_text": round_text,
        "tool_calls": tool_calls,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
    }


async def tools_node(state: AgentState, config: RunnableConfig) -> dict:
    from app.debug.trace_logger import trace_log

    cfg = config["configurable"]
    trace = cfg["trace"]
    lang = state["lang"]
    round_text = state["round_text"]
    tool_calls = state["tool_calls"]
    round_num = state["round"] - 1     # `model` already advanced the counter
    result = _round_result(state)

    # `history` is the live view tools read (`_messages`); `new_messages`
    # is the delta the reducer concatenates onto state.
    history = list(state["messages"])
    new_messages: list[dict] = []

    def _append(msg: dict) -> None:
        history.append(msg)
        new_messages.append(msg)

    _append({
        "role": "assistant",
        "content": round_text or None,
        "tool_calls": tool_calls,
    })

    # If introduce_product is among the tool calls, skip all other tools
    # (LLM sometimes incorrectly records events when user is just asking about features)
    tool_names_in_round = {tc["function"]["name"] for tc in tool_calls}
    if "introduce_product" in tool_names_in_round and len(tool_calls) > 1:
        tool_calls = [tc for tc in tool_calls if tc["function"]["name"] == "introduce_product"]

    tool_results_map = {}  # tc_name → tool_result for skip_round2 check
    deferred: list[dict] = []
    for tc in tool_calls:
        tc_name = tc["function"]["name"]
        tc_args_str = tc["function"]["arguments"]

        trace_log("tool_call", round=round_num, data={
            "tool_name": tc_name,
            "arguments": tc_args_str,
        })
        trace.record_event("tool_call_started", {
            "round": round_num,
            "tool": tc_name,
            "args": tc_args_str,
        })

        tool_result = await dispatch_tool(
            tc, cfg["db"], cfg["user_id"], cfg["session_id"], result, _emit_card, lang,
            pets=state.get("pets"), images=cfg.get("images"),
            image_urls=state.get("image_urls"),
            recent_image_urls=state.get("recent_image_urls"),
            location=state.get("location"), _messages=history,
            confirm_action_id=cfg.get("thread_id", ""),
        )

        tool_results_map[tc_name] = tool_result

        _serialized_result = {k: v for k, v in tool_result.items() if not k.startswith("_")}
        # Size guard per spec §5.3: cap each trace entry at 64 KB.
        _payload = json.dumps(_serialized_result, ensure_ascii=False, default=str)
        if len(_payload) > 64_000:
            _serialized_result = {"_truncated": True, "_size": len(_payload), "keys": list(_serialized_result.keys())}

        trace_log("tool_result", round=round_num, data={
            "tool_name": tc_name,
            "success": tool_result.get("success"),
            "error": tool_result.get("error"),
            "result_keys": list(tool_result.keys()),
            "result": _serialized_result,     # NEW — full value with card
        })

        trace.record("tool_dispatch", {
            "round": round_num,
            "tool": tc["function"]["name"],
            "args": tc["function"]["arguments"],
            "result_keys": list(tool_result.keys()),
            "success": tool_result.get("success"),
            "error": tool_result.get("error"),
        })
        trace.record_event("tool_call_completed", {
            "round": round_num,
            "tool": tc_name,
            "success": tool_result.get("success"),
            "error": tool_result.get("error"),
            "result_keys": list(tool_result.keys()),
        })

        # Confirm gate: park the call for the `confirm` node instead of
        # executing it (or, for update_pet_profile, park the locked-field
        # re-run). The tool message is appended by `confirm` once the user
        # has answered, so nothing here has to be undone on resume.
        confirm_card = tool_result.get("_confirm_card")
        if confirm_card is not None:
            deferred.append({
                "card": confirm_card,
                "tool_name": tool_result.get("_confirm_tool", tc_name),
                "arguments": tool_result.get("_confirm_arguments", json.loads(tc_args_str or "{}")),
                "tool_call_id": tc["id"],
            })
            result.confirm_cards.append(confirm_card)
            continue

        # Strip internal markers (keys starting with _) before serialising
        # back to the LLM — those are private to the orchestrator.
        serializable = {k: v for k, v in tool_result.items() if not k.startswith("_")}
        _append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": json.dumps(serializable, ensure_ascii=False, default=str),
        })

        # request_images sentinel — wrap base64 payloads in an OpenAI-
        # style multimodal user message so the LLM actually sees them
        # on the next round.
        if "_inject_images" in tool_result:
            image_content = [
                {"type": "text", "text": "这是用户附带的图片，请仔细查看后回答：" if lang == "zh" else "Here are the user's images:"}
            ]
            for img_b64 in tool_result["_inject_images"]:
                image_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                })
            _append({"role": "user", "content": image_content})

    # --- Skip Round 2: if all tools are simple CRUD and succeeded,
    # use the LLM's Round 1 streaming text as the final response.
    # This saves ~8000 prompt tokens per skipped round. ---
    skip = _can_skip_round2(tool_calls, tool_results_map, result, round_text)
    if skip:
        trace.record("skip_round2", {
            "round": round_num,
            "tools": list(tool_names_in_round),
        })
        logger.info("skip_round2", extra={
            "round": round_num,
            "tools": list(tool_names_in_round),
        })

    return {
        "messages": new_messages,
        "text_parts": [round_text],
        "cards": result.cards,
        "confirm_cards": result.confirm_cards,
        "tools_called": result.tools_called,
        "tools_executed": result.tools_executed,
        "plan_steps": result.plan_steps,
        "skip_round2": skip,
        "deferred_confirms": deferred,
    }


async def confirm_node(state: AgentState, config: RunnableConfig) -> dict:
    """Pause on one deferred tool call until the user answers the card.

    LangGraph re-runs this node from the top when the run is resumed, so
    everything above `interrupt()` must stay side-effect free — it is: the
    card was already built (and checkpointed) by `tools`. Everything below
    runs exactly once, on the resume pass.
    """
    cfg = config["configurable"]
    trace = cfg["trace"]
    deferred = list(state.get("deferred_confirms") or [])
    entry, rest = deferred[0], deferred[1:]

    trace.record("interrupt", {
        "tool": entry["tool_name"],
        "action_id": entry["card"].get("action_id", ""),
    })
    approved = interrupt(entry["card"])

    # --- resume path only ---
    trace.record("resume", {"tool": entry["tool_name"], "approved": approved is True})

    result = _round_result(state)
    if approved is not True:
        tool_result = {"status": "cancelled", "executed": False}
    else:
        args = dict(entry["arguments"])
        # The user already tapped confirm — force-lock the lockable fields so
        # update_pet_profile doesn't bounce back into another confirm card.
        if entry["tool_name"] == "update_pet_profile":
            args.setdefault("_force_lock", True)
        result.tools_called.add(entry["tool_name"])
        tool_result = await handle_tool_execution(
            ToolInvocation(id=entry["tool_call_id"], name=entry["tool_name"], arguments=args),
            ToolDispatchContext(
                db=cfg["db"],
                user_id=cfg["user_id"],
                session_id=cfg["session_id"],
                result=result,
                on_card=_emit_card,
                lang=state["lang"],
                pets=state.get("pets"),
                images=cfg.get("images"),
                image_urls=state.get("image_urls"),
                recent_image_urls=state.get("recent_image_urls"),
                location=state.get("location"),
                confirm_action_id=entry["card"].get("action_id", ""),
            ),
        )

    # Defensive: after a confirmed run the tool must not ask again (a missing
    # _force_lock would loop update_pet_profile back into a card). Surface it
    # instead of telling the client "success".
    reentrant = bool(tool_result.get("needs_confirm"))
    if reentrant:
        logger.error("confirm_action_reentrant_needs_confirm", extra={
            "action_id": entry["card"].get("action_id", ""),
            "tool": entry["tool_name"],
            "arguments_keys": list(entry["arguments"].keys()),
        })

    serializable = {k: v for k, v in tool_result.items() if not k.startswith("_")}
    return {
        "messages": [{
            "role": "tool",
            "tool_call_id": entry["tool_call_id"],
            "content": json.dumps(serializable, ensure_ascii=False, default=str),
        }],
        "deferred_confirms": rest,
        "cards": result.cards,
        "tools_called": result.tools_called,
        "tools_executed": result.tools_executed,
        "resumed": True,
        "confirm_error": bool(tool_result.get("error")),
        "confirm_success": bool(tool_result.get("success", not tool_result.get("error"))),
        "confirm_reentrant": reentrant,
    }


def review_node(state: AgentState, config: RunnableConfig) -> dict:
    """No tool_calls this round — decide: plan nag → write-claim nag → nudge → exit."""
    trace = config["configurable"]["trace"]
    lang = state["lang"]
    round_text = state["round_text"]
    round_num = state["round"] - 1
    new_messages: list[dict] = []
    tools_called = state.get("tools_called") or set()
    plan_steps = state.get("plan_steps") or []

    # Plan nag: if plan() declared steps but the LLM stopped before
    # executing all of them, inject a nag message and retry once.
    if not state.get("plan_nag_used") and plan_steps:
        planned_tools = {s["tool"] for s in plan_steps}
        # Exclude plan itself when checking what still needs to run
        executed_tools = tools_called - {"plan"}
        missing_tools = planned_tools - executed_tools
        if missing_tools:
            missing_steps = [s for s in plan_steps if s["tool"] in missing_tools]
            trace.record("plan_nag_triggered", {
                "round": round_num,
                "missing_tools": list(missing_tools),
                "missing_steps": missing_steps,
            })
            logger.info("plan_nag_triggered", extra={
                "round": round_num,
                "missing_tools": list(missing_tools),
            })
            # Preserve last round's text so the nag message reads
            # naturally in the conversation history the LLM sees.
            if round_text:
                new_messages.append({"role": "assistant", "content": round_text})
            step_list = "\n".join(f"- [{s['id']}] {s['action']} → {s['tool']}" for s in missing_steps)
            if lang == "zh":
                nag = f"你的 plan 还有未完成的步骤:\n{step_list}\n请立即调用对应的工具完成这些步骤。"
            else:
                nag = f"Your plan has unfinished steps:\n{step_list}\nPlease call the corresponding tools now."
            new_messages.append({"role": "user", "content": nag})
            return {
                "messages": new_messages,
                "text_parts": [round_text],
                "plan_nag_used": True,
                "retry": True,
            }

    # Write-claim guard: LLM's final text claims a write happened
    # (已更新/已删除/updated/deleted) but no write tool ACTUALLY executed
    # this whole run (only queries, or everything was deferred behind
    # confirm cards, or tools errored). Force one more round.
    if not state.get("write_claim_nag_used"):
        has_write = bool((state.get("tools_executed") or set()) & _WRITE_TOOLS)
        accumulated_text = "".join(state.get("text_parts") or []) + round_text
        if not has_write and _text_claims_write(accumulated_text, lang):
            trace.record("write_claim_nag_triggered", {
                "round": round_num,
                "tools_called": list(tools_called),
                "text_sample": accumulated_text[-200:],
            })
            logger.warning("write_claim_nag_triggered", extra={
                "round": round_num,
                "tools_called": list(tools_called),
            })
            _inject_write_claim_nag(new_messages, round_text, lang)
            # Drop the fabricated text (never enters text_parts) so the final
            # response reflects the real (next-round) outcome.
            return {
                "messages": new_messages,
                "write_claim_nag_used": True,
                "retry": True,
            }

    # Nudge: only fire when the LLM called zero tools. If it called
    # *some* tool (even a different one than suggested) it's clearly
    # working — don't second-guess it.
    if not state.get("nudge_used") and not tools_called and state.get("suggested_actions"):
        missed = _find_missed_tools(state["suggested_actions"], tools_called)
        if missed:
            trace.record("nudge_triggered", {
                "round": round_num,
                "missed_tools": [a["tool_name"] for a in missed],
            })
            logger.info("nudge_triggered", extra={
                "round": round_num,
                "missed_tools": [a["tool_name"] for a in missed],
            })
            _inject_nudge(new_messages, round_text, missed, lang)
            return {
                "messages": new_messages,
                "text_parts": [round_text],
                "nudge_used": True,
                "retry": True,
            }

    # Normal exit — no tools, no pending plan, no nudge
    return {"text_parts": [round_text], "retry": False}


def finalize_node(state: AgentState, config: RunnableConfig) -> dict:
    trace = config["configurable"]["trace"]
    lang = state["lang"]
    tools_called = state.get("tools_called") or set()
    tools_executed = state.get("tools_executed") or set()
    cards = state.get("cards") or []
    confirm_cards = state.get("confirm_cards") or []
    new_cards = []

    # Ensure response_text is non-empty unless the only output is a confirm
    # card (in which case the card itself is the "reply"). This guarantees
    # the user never sees a blank bubble.
    raw_text = "".join(state.get("text_parts") or [])
    # Strip leaked XML/HTML tags from LLM output (grok sometimes outputs <parameter> or <xai:function_call>)
    response_text = re.sub(r"</?(?:parameter|xai:function_call|function_call)[^>]*>", "", raw_text).strip()

    # Final fabrication guard: if the LLM's response claims a write ("已删除
    # /updated") but no write tool actually executed AND no confirm card is
    # pending (the card itself would signal "pending" correctly), replace the
    # fabricated text with an honest failure message and emit a warning card.
    # This is Level 2 "UI truth" — users should never see a lie.
    has_real_write = bool(tools_executed & _WRITE_TOOLS)
    has_pending_confirm = bool(confirm_cards)
    if (
        not has_real_write
        and not has_pending_confirm
        and _text_claims_write(response_text, lang)
    ):
        logger.warning("fabrication_blocked", extra={
            "tools_called": list(tools_called),
            "tools_executed": list(tools_executed),
            "text_sample": response_text[:200],
        })
        trace.record("fabrication_blocked", {
            "tools_called": list(tools_called),
            "tools_executed": list(tools_executed),
            "text_sample": response_text[:200],
        })
        if lang == "zh":
            honest = (
                "抱歉，这条操作我没能成功执行 😔\n"
                "请再说一次您的请求，或者在日历/档案里手动操作。"
            )
            warn_message = "操作未能完成，数据库未变更"
        else:
            honest = (
                "Sorry — I couldn't actually execute that action 😔\n"
                "Please try saying it again, or do it manually in the calendar / profile."
            )
            warn_message = "Action did not complete — database unchanged"
        response_text = honest
        warning_card = {
            "type": "warning",
            "severity": "error",
            "message": warn_message,
        }
        new_cards.append(warning_card)
        _emit_card(warning_card)

    if not response_text.strip() and not confirm_cards and not cards:
        fallback = t("fallback_error", lang)
        response_text = fallback
        _emit_token(fallback)

    trace.record_event("run_completed", {
        "tools_called": sorted(tools_called),
        "tools_executed": sorted(tools_executed),
        "cards_count": len(cards) + len(new_cards),
        "confirm_cards_count": len(confirm_cards),
        "prompt_tokens": state.get("prompt_tokens", 0),
        "completion_tokens": state.get("completion_tokens", 0),
    })

    return {"response_text": response_text, "cards": new_cards}


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------

def _after_model(state: AgentState) -> str:
    return "tools" if state.get("tool_calls") else "review"


def _after_tools(state: AgentState) -> str:
    if state.get("deferred_confirms"):
        return "confirm"
    if state.get("skip_round2") or state["round"] >= MAX_ROUNDS:
        return "finalize"
    return "model"


def _after_confirm(state: AgentState) -> str:
    if state.get("deferred_confirms"):
        return "confirm"
    # Straight to finalize: the user already saw the card and only gets the
    # executed tool's card back, so a second model round buys nothing. The
    # one exception is a failure the user needs explained.
    if state.get("confirm_error") and state["round"] < MAX_ROUNDS:
        return "model"
    return "finalize"


def _after_review(state: AgentState) -> str:
    if state.get("retry") and state["round"] < MAX_ROUNDS:
        return "model"
    return "finalize"


def build_graph(checkpointer=None):
    builder = StateGraph(AgentState)
    builder.add_node("prepare", prepare_node)
    builder.add_node("model", model_node)
    builder.add_node("tools", tools_node)
    builder.add_node("confirm", confirm_node)
    builder.add_node("review", review_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "model")
    builder.add_conditional_edges("model", _after_model, ["tools", "review"])
    builder.add_conditional_edges("tools", _after_tools, ["confirm", "model", "finalize"])
    builder.add_conditional_edges("confirm", _after_confirm, ["confirm", "model", "finalize"])
    builder.add_conditional_edges("review", _after_review, ["model", "finalize"])
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)


# `interrupt()` needs a checkpointer; when Postgres isn't configured (tests,
# harness, or a failed setup) an in-process saver keeps the graph runnable.
FALLBACK_CHECKPOINTER = InMemorySaver()

_GRAPHS: dict[int, Any] = {}


def get_graph(checkpointer=None):
    """Compiled graph for this checkpointer (compilation is pure, so cache)."""
    saver = checkpointer or FALLBACK_CHECKPOINTER
    key = id(saver)
    if key not in _GRAPHS:
        _GRAPHS[key] = build_graph(saver)
    return _GRAPHS[key]


# ---------------------------------------------------------------------------
# stream_agent — entry point: yields ("sse", event) then ("result", result)
# ---------------------------------------------------------------------------

def new_thread_id(user_id) -> str:
    """One checkpoint thread per chat turn: `"<user_id>:<correlation_id>"`."""
    return f"{user_id}:{get_correlation_id() or uuid.uuid4().hex}"


def _interrupt_cards(chunk: Any) -> list[dict]:
    """Confirm cards carried by an `updates` chunk's `__interrupt__` entry."""
    if not isinstance(chunk, dict):
        return []
    return [
        i.value for i in chunk.get("__interrupt__", ())
        if isinstance(getattr(i, "value", None), dict)
    ]


# `updates` chunks carry per-node deltas, so the accumulator has to re-apply
# the same reducers AgentState declares.
_ACC_ADD = ("cards", "confirm_cards", "prompt_tokens", "completion_tokens")
_ACC_UNION = ("tools_called", "tools_executed")
_ACC_LAST = ("plan_steps", "response_text")


def _accumulate(acc: dict, chunk: dict) -> None:
    """Fold one `updates` chunk into `acc`.

    Non-node entries (e.g. `__interrupt__`) carry a non-dict payload and are
    skipped rather than crashing the run.
    """
    if not isinstance(chunk, dict):
        return
    for update in chunk.values():
        if not isinstance(update, dict):
            continue
        for key in _ACC_ADD:
            if key in update:
                acc[key] = acc[key] + update[key]
        for key in _ACC_UNION:
            if key in update:
                acc[key] = acc[key] | set(update[key])
        for key in _ACC_LAST:
            if key in update:
                acc[key] = update[key]

async def stream_agent(
    *,
    system_prompt: str,
    context_messages: list[dict],
    model: str | None = None,
    db=None,
    user_id=None,
    session_id=None,
    lang: str = "zh",
    today: str = "",
    suggested_actions: list | None = None,
    trace=INACTIVE_TRACE,
    graph=None,
    thread_id: str | None = None,
    images: list[str] | None = None,
    image_urls: list[str] | None = None,
    recent_image_urls: list[str] | None = None,
    location: dict | None = None,
    pets: list | None = None,
) -> AsyncIterator[tuple[str, Any]]:
    """Run the agent graph, yielding ("sse", {event, data}) as they happen.

    The last item is always ("result", OrchestratorResult).

    One turn = one checkpoint thread, `"<user_id>:<correlation_id>"`. The
    confirm card carries it as `action_id`, and `/chat/confirm-action` resumes
    the run from it.
    """
    use_model = model or settings.model
    thread_id = thread_id or new_thread_id(user_id)
    initial: AgentState = {
        "system_prompt": system_prompt,
        "context_messages": context_messages,
        "messages": [],
        "round": 0,
        "round_text": "",
        "tool_calls": [],
        "nudge_used": False,
        "plan_nag_used": False,
        "write_claim_nag_used": False,
        "plan_steps": [],
        "retry": False,
        "skip_round2": False,
        "deferred_confirms": [],
        "resumed": False,
        "confirm_error": False,
        "text_parts": [],
        "cards": [],
        "confirm_cards": [],
        "tools_called": set(),
        "tools_executed": set(),
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "response_text": "",
        "lang": lang,
        "session_id": str(session_id) if session_id else "",
        "today": today,
        "pets": [_pet_to_dict(p) for p in pets] if pets else pets,
        "location": location,
        "image_urls": image_urls,
        "recent_image_urls": recent_image_urls,
        "suggested_actions": [_action_to_dict(a) for a in (suggested_actions or [])],
    }
    config = {
        "configurable": {
            "thread_id": thread_id,
            "db": db,
            "user_id": user_id,
            "session_id": session_id,
            "trace": trace,
            "model": use_model,
            "vision_model": settings.vision_model or use_model,
            # Per-request, read-only, and large — kept out of the state so a
            # checkpoint never stores raw base64. (The multimodal user message
            # `_inject_images` appends still carries the bytes; see Phase 2b.)
            "images": images,
        },
        "recursion_limit": 4 * MAX_ROUNDS + 10,
    }

    acc = {
        "cards": [],
        "confirm_cards": [],
        "tools_called": set(),
        "tools_executed": set(),
        "plan_steps": [],
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "response_text": "",
    }
    async for mode, chunk in (graph or get_graph()).astream(
        initial, config, stream_mode=["custom", "updates"]
    ):
        if mode == "custom":
            yield ("sse", chunk)
        else:
            # The confirm node paused: surface its card exactly as `on_card`
            # would have, then let the stream end normally.
            for card in _interrupt_cards(chunk):
                yield ("sse", {"event": "card", "data": card})
            _accumulate(acc, chunk)

    result = OrchestratorResult(
        response_text=acc["response_text"],
        cards=acc["cards"],
        confirm_cards=acc["confirm_cards"],
        tools_called=acc["tools_called"],
        tools_executed=acc["tools_executed"],
        plan_steps=acc["plan_steps"],
        total_prompt_tokens=acc["prompt_tokens"],
        total_completion_tokens=acc["completion_tokens"],
        model_used=use_model,
    )
    yield ("result", result)
