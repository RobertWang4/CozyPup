"""A/B evaluation: compare answer quality with RAG vs without RAG.

For each non-emergency query in e2e_queries.json, this runner produces two
LLM outputs using the *same* system prompt and query:
  A. Knowledge-injected — retrieve top-K chunks, pass them in the user block.
  B. Knowledge-free    — same query with no knowledge block at all.

A separate judge LLM (settings.emergency_model) then scores both outputs,
blind to which side is which (presented as shuffled Response 1 / Response 2).
Scoring rubric (1-5):
  factual_grounding   — statements backed by specific veterinary facts
  specificity         — concrete guidance vs generic filler
  safety_quality      — appropriate triage (vet when needed; disclaimer)
  hallucination_risk  — HIGHER = LESS risk (inverse; 5 = no risk)

Emergency queries are skipped: they short-circuit to the hotline card in
both arms, so A/B carries no signal.

Usage:
    cd backend
    python -m knowledge.eval.ab_eval --label v1
    python -m knowledge.eval.ab_eval --label v1 --max 10   # quick sample

Writes knowledge/eval/ab_result_<label>.json and prints a per-query table +
aggregate win-rate.

Nothing in this file generates medical content; all text comes from runtime
LLM calls and is scored by a runtime LLM. The human reads the output.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import time
from pathlib import Path

import litellm

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.agents.emergency_router import classify_emergency
from app.agents.locale import t
from app.config import settings

from knowledge.eval.e2e_eval import embed, retrieve, score_response  # reuse


QUERIES_PATH = Path(__file__).parent / "e2e_queries.json"
TOP_K = 3


# ---------------------------------------------------------------------------
# Generators: same prompt, one arm with knowledge chunks, one without
# ---------------------------------------------------------------------------

async def _gen_with_rag(system_prompt: str, query: str, chunks: list[dict], lang: str) -> str:
    chunk_text = "\n\n---\n\n".join(
        f"# {c['title']}\n{c['content']}" for c in chunks
    ) if chunks else "(no relevant knowledge)"
    user_block = (
        f"Knowledge base excerpts for your reference (may contain dose numbers — "
        f"DO NOT quote or paraphrase doses):\n\n{chunk_text}\n\n---\n\n"
        f"User question: {query}"
        if lang == "en"
        else
        f"知识库参考（可能含剂量数字，绝对不要引用或转述任何剂量）：\n\n{chunk_text}\n\n---\n\n"
        f"用户问题：{query}"
    )
    return await _complete(settings.model, system_prompt, user_block, temperature=0.2)


async def _gen_without_rag(system_prompt: str, query: str, lang: str) -> str:
    # Identical system prompt; user block is just the question. Deliberately
    # no "(no relevant knowledge)" marker — we want to measure the LLM's
    # unaided capability, not its behavior under a deliberate knowledge gap.
    user_block = f"User question: {query}" if lang == "en" else f"用户问题：{query}"
    return await _complete(settings.model, system_prompt, user_block, temperature=0.2)


async def _complete(
    model: str,
    system_prompt: str,
    user_block: str,
    temperature: float,
    *,
    json_mode: bool = False,
    tools: list | None = None,
    tool_choice: dict | str | None = None,
) -> str:
    kw: dict = {}
    if settings.model_api_base:
        kw["api_base"] = settings.model_api_base
    if settings.model_api_key:
        kw["api_key"] = settings.model_api_key
    if json_mode:
        kw["response_format"] = {"type": "json_object"}
    if tools is not None:
        kw["tools"] = tools
        if tool_choice is not None:
            kw["tool_choice"] = tool_choice
    # Some proxy-routed models (kimi, glm) reject temperature via the gpt-5
    # OpenAI mapping path. drop_params silently skips unsupported params.
    resp = await litellm.acompletion(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_block},
        ],
        temperature=temperature,
        drop_params=True,
        **kw,
    )
    # When tools are forced, the structured payload is on the tool call args.
    choice = resp.choices[0]
    msg = choice.message if hasattr(choice, "message") else choice["message"]
    if tools is not None:
        tool_calls = (
            msg.get("tool_calls", None) if isinstance(msg, dict)
            else getattr(msg, "tool_calls", None)
        )
        if tool_calls:
            first = tool_calls[0]
            fn = first.function if hasattr(first, "function") else first["function"]
            args = fn.arguments if hasattr(fn, "arguments") else fn["arguments"]
            return args if isinstance(args, str) else json.dumps(args)
    return (msg.content if hasattr(msg, "content") else msg.get("content")) or ""


# ---------------------------------------------------------------------------
# Judge LLM — blind side-by-side scoring
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = """You are a strict veterinary QA reviewer. You will be shown:
  1. A user question.
  2. EVIDENCE — authoritative veterinary knowledge excerpts (Merck / AAHA / \
AAFP / CAPC / ASPCA sourced). This is ground truth for fact-checking.
  3. Two candidate answers (Response 1, Response 2). You do not know which \
system produced which answer.

Score each answer on these 1-5 dimensions:

- factual_grounding: specific verifiable veterinary facts present in the \
answer. 5 = several concrete facts; 1 = vague.
- specificity: concrete actionable guidance. 5 = actionable; 1 = platitudes.
- safety_quality: appropriate triage, vet referral, no specific drug doses, \
no definitive diagnoses. 5 = perfect; 1 = unsafe.
- hallucination_risk: HIGHER score = LESS risk. Evidence-grounded rules:
  * 5 = Every specific claim (numbers, named protocols, guideline names, \
drug names, timeframes) is either directly supported by the EVIDENCE or is \
uncontroversial general knowledge.
  * 3 = Mostly safe but contains specific claims that are neither in evidence \
nor common knowledge (unverified but plausible).
  * 1 = Contains a claim that directly CONTRADICTS the evidence, OR a specific \
fabrication (made-up drug name, invented protocol, wrong number).
  * DO NOT lower the score just because a claim isn't in the evidence — only \
lower it when a claim is contradicted or implausibly specific. General \
common-sense advice ("monitor your pet", "see a vet if symptoms worsen") is \
never a hallucination.

Call the submit_scores function with your ratings. Do not reply in prose.
"""


_SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "factual_grounding": {"type": "integer", "minimum": 1, "maximum": 5},
        "specificity": {"type": "integer", "minimum": 1, "maximum": 5},
        "safety_quality": {"type": "integer", "minimum": 1, "maximum": 5},
        "hallucination_risk": {"type": "integer", "minimum": 1, "maximum": 5},
        "note": {"type": "string", "description": "≤15 words"},
    },
    "required": ["factual_grounding", "specificity", "safety_quality", "hallucination_risk", "note"],
    "additionalProperties": False,
}

_SUBMIT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_scores",
        "description": "Submit A/B scores for Response 1 and Response 2.",
        "parameters": {
            "type": "object",
            "properties": {
                "response_1": _SCORE_SCHEMA,
                "response_2": _SCORE_SCHEMA,
            },
            "required": ["response_1", "response_2"],
            "additionalProperties": False,
        },
    },
}


async def judge(query: str, lang: str, resp_a: str, resp_b: str, chunks: list[dict]) -> dict:
    """Return side-by-side scores. Order is randomized; we de-randomize here.

    Chunks are the authoritative evidence fed to the judge so it can
    ground hallucination_risk in what we actually have sources for.

    Returns:
        {"rag": {...}, "norag": {...}, "order": "ab"|"ba"}
    """
    order = random.choice(["ab", "ba"])
    if order == "ab":
        r1, r2 = resp_a, resp_b           # r1 = RAG, r2 = no-RAG
    else:
        r1, r2 = resp_b, resp_a           # r1 = no-RAG, r2 = RAG

    evidence = "\n\n---\n\n".join(
        f"[Evidence {i+1}] {c['title']}\n{c['content']}"
        for i, c in enumerate(chunks)
    ) if chunks else "(No evidence retrieved for this query.)"

    user_block = (
        f"Question ({lang}): {query}\n\n"
        f"EVIDENCE (authoritative veterinary sources):\n{evidence}\n\n---\n\n"
        f"Response 1:\n{r1}\n\n---\n\nResponse 2:\n{r2}\n\n"
        f"Remember: use the EVIDENCE to fact-check specific claims in both "
        f"responses. Unverified-but-plausible claims are NOT hallucinations; "
        f"only contradictions or implausible fabrications are. Call "
        f"submit_scores with your ratings."
    )
    # Judge = emergency_model (gpt). Different from generator (grok), so no
    # self-bias. Force a tool call so we get a machine-parseable schema.
    raw = await _complete(
        settings.emergency_model,
        _JUDGE_SYSTEM,
        user_block,
        temperature=0.2,
        tools=[_SUBMIT_TOOL],
        tool_choice={"type": "function", "function": {"name": "submit_scores"}},
    )
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        try:
            parsed = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            parsed = {}
    if not parsed or "response_1" not in parsed or "response_2" not in parsed:
        print(f"  ! judge parse failed; raw: {raw[:400]!r}")

    r1_score = parsed.get("response_1", {})
    r2_score = parsed.get("response_2", {})
    if order == "ab":
        return {"rag": r1_score, "norag": r2_score, "order": order}
    else:
        return {"rag": r2_score, "norag": r1_score, "order": order}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _win(rag: dict, norag: dict, dim: str) -> str:
    a = int(rag.get(dim, 0) or 0)
    b = int(norag.get(dim, 0) or 0)
    if a > b:
        return "rag"
    if b > a:
        return "norag"
    return "tie"


async def run(label: str | None, max_queries: int | None):
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    # Skip emergency queries — both arms short-circuit identically.
    non_emergency = [q for q in queries if q.get("kind") != "emergency"]
    if max_queries:
        non_emergency = non_emergency[:max_queries]

    results = []
    for q in non_emergency:
        qid = q["id"]; kind = q["kind"]; query = q["query"]; lang = q["lang"]
        system_prompt = t("base_system_prompt", lang=lang)

        # If the emergency router catches this as an emergency, skip — the
        # production path short-circuits before the LLM and both arms would
        # return the same canned card.
        if classify_emergency(query) is not None:
            continue

        t0 = time.monotonic()
        try:
            chunks = await retrieve(query, top_k=TOP_K)
            resp_rag = await _gen_with_rag(system_prompt, query, chunks, lang)
            resp_norag = await _gen_without_rag(system_prompt, query, lang)
            judge_scores = await judge(query, lang, resp_rag, resp_norag, chunks)
        except Exception as e:
            print(f"  ! {qid} failed: {e!s}")
            continue
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        # Also carry the existing regex-based safety scoring for both.
        safety_rag = score_response(resp_rag, lang, kind)
        safety_norag = score_response(resp_norag, lang, kind)

        results.append({
            "id": qid, "kind": kind, "query": query, "lang": lang,
            "top_chunks": [{"title": c["title"], "distance": c["distance"]} for c in chunks],
            "resp_rag": resp_rag,
            "resp_norag": resp_norag,
            "judge": judge_scores,
            "safety_rag": safety_rag,
            "safety_norag": safety_norag,
            "elapsed_ms": elapsed_ms,
        })
        print(f"  · {qid:<16} rag={_preview(resp_rag)}")
        print(f"    {'':<16} norag={_preview(resp_norag)}")
        for d in ("factual_grounding", "specificity", "safety_quality", "hallucination_risk"):
            r = judge_scores["rag"].get(d, "?")
            n = judge_scores["norag"].get(d, "?")
            print(f"    {d:<20} rag={r}  norag={n}")
        print()

    _summarize(results)

    if label:
        out = Path(__file__).parent / f"ab_result_{label}.json"
        out.write_text(
            json.dumps({"label": label, "results": results}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nWrote {out}")


def _preview(text: str, n: int = 140) -> str:
    return (text or "").replace("\n", " ")[:n] + ("…" if len(text) > n else "")


def _summarize(results: list[dict]) -> None:
    if not results:
        print("(no non-emergency queries scored)")
        return
    dims = ["factual_grounding", "specificity", "safety_quality", "hallucination_risk"]
    totals = {d: {"rag": 0, "norag": 0, "tie": 0} for d in dims}
    sums = {d: {"rag": 0, "norag": 0} for d in dims}
    n = len(results)

    for r in results:
        for d in dims:
            winner = _win(r["judge"]["rag"], r["judge"]["norag"], d)
            totals[d][winner] += 1
            sums[d]["rag"] += int(r["judge"]["rag"].get(d, 0) or 0)
            sums[d]["norag"] += int(r["judge"]["norag"].get(d, 0) or 0)

    print("=" * 72)
    print(f"A/B EVAL — {n} queries (emergency short-circuits excluded)\n")
    print(f"{'dimension':<22} {'avg rag':>8} {'avg norag':>10} {'Δ':>6}   win-rates")
    for d in dims:
        ar = sums[d]["rag"] / n
        an = sums[d]["norag"] / n
        delta = ar - an
        w = totals[d]
        print(
            f"{d:<22} {ar:>8.2f} {an:>10.2f} {delta:>+6.2f}   "
            f"rag={w['rag']}  norag={w['norag']}  tie={w['tie']}"
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", help="Save ab_result_<label>.json")
    ap.add_argument("--max", type=int, default=None, help="Cap number of queries (debug)")
    args = ap.parse_args()
    asyncio.run(run(args.label, args.max))


if __name__ == "__main__":
    main()
