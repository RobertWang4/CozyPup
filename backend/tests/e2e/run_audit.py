#!/usr/bin/env python3
"""E2E Audit Runner — runs every TEST_PLAN case, captures full LLM traces, generates report.

Usage:
    cd backend
    # Start backend first: uvicorn app.main:app --reload --port 8000
    python tests/e2e/run_audit.py [--base-url http://localhost:8000] [--lang zh]
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tests.e2e.conftest import E2EClient, ChatResult, today_str, yesterday_str
from tests.e2e.test_messages import MESSAGES


# ---------------------------------------------------------------------------
# Test case definitions — maps TEST_PLAN item to execution config
# ---------------------------------------------------------------------------

class TestCase:
    def __init__(self, case_id: str, name: str, message: str | list[str],
                 setup: str | None = None, needs_pet: bool = False,
                 needs_two_pets: bool = False, no_pet: bool = False,
                 location: dict | None = None,
                 check=None, depends_on: str | None = None):
        self.case_id = case_id
        self.name = name
        self.message = message  # str or list[str] for sequences
        self.setup = setup  # setup message to run before the test
        self.needs_pet = needs_pet
        self.needs_two_pets = needs_two_pets
        self.no_pet = no_pet  # explicitly no pet
        self.location = location
        self.check = check  # validation function(result, client) -> (pass, reason)
        self.depends_on = depends_on


def build_test_cases(lang: str) -> list[TestCase]:
    """Build all test cases from TEST_PLAN, parametrized by language."""
    m = MESSAGES
    ottawa_loc = {"lat": 45.4215, "lng": -75.6972}

    cases = [
        # === Section 1: Basic Chat ===
        TestCase("1.1", "基础聊天", m["1.1"][lang], no_pet=True,
                 check=lambda r, c: (bool(r.text.strip()), f"text={'(empty)' if not r.text.strip() else 'ok'}")),
        TestCase("1.2", "中文回复检测", m["1.2"][lang], no_pet=True,
                 check=lambda r, c: (bool(r.text.strip()), f"text_len={len(r.text)}")),
        TestCase("1.3", "多轮闲聊", m["1.3_seq"][lang], no_pet=True,
                 check=lambda r, c: (bool(r.text.strip()), "last msg has text")),

        # === Section 2: Create Calendar Events ===
        TestCase("2.1", "记录饮食事件", m["2.1"][lang], needs_pet=True,
                 check=lambda r, c: (r.has_card("record"), f"cards={[x.get('type') for x in r.cards]}")),
        TestCase("2.2", "记录日常事件(昨天)", m["2.2"][lang], needs_pet=True,
                 check=lambda r, c: (r.has_card("record"), f"cards={[x.get('type') for x in r.cards]}")),
        TestCase("2.3", "记录医疗事件", m["2.3"][lang], needs_pet=True,
                 check=lambda r, c: (r.has_card("record"), f"cards={[x.get('type') for x in r.cards]}")),
        TestCase("2.4", "模糊日期追问", m["2.4"][lang], needs_pet=True,
                 check=lambda r, c: (not r.has_card("record") and ("?" in r.text or "？" in r.text or "哪" in r.text or "when" in r.text.lower()), f"text_preview={r.text[:80]}")),
        TestCase("2.5", "指定日期记录", m["2.5"][lang], needs_pet=True,
                 check=lambda r, c: (r.has_card("record"), f"cards={[x.get('type') for x in r.cards]}")),
        TestCase("2.6", "异常事件", m["2.6"][lang], needs_pet=True,
                 check=lambda r, c: (r.has_card("record"), f"cards={[x.get('type') for x in r.cards]}")),
        TestCase("2.7", "多事件同时记录", m["2.7"][lang], needs_pet=True,
                 check=lambda r, c: (r.card_count("record") >= 2, f"record_count={r.card_count('record')}")),
        TestCase("2.8", "拉稀→abnormal", m["2.8"][lang], needs_pet=True,
                 check=lambda r, c: (r.has_card("record"), f"cards={[x.get('type') for x in r.cards]}")),
        TestCase("2.9", "驱虫→medical", m["2.9"][lang], needs_pet=True,
                 check=lambda r, c: (r.has_card("record"), f"cards={[x.get('type') for x in r.cards]}")),
        TestCase("2.10", "游泳→daily", m["2.10"][lang], needs_pet=True,
                 check=lambda r, c: (r.has_card("record"), f"cards={[x.get('type') for x in r.cards]}")),

        # === Section 3: Query Events ===
        TestCase("3.1", "查询疫苗记录", m["3.1"][lang], needs_pet=True,
                 setup=m["2.3"][lang],  # create vaccine record first
                 check=lambda r, c: (bool(r.text.strip()), f"text_len={len(r.text)}")),
        TestCase("3.2", "查询本周记录", m["3.2"][lang], needs_pet=True,
                 setup=m["2.1"][lang],
                 check=lambda r, c: (bool(r.text.strip()), f"text_len={len(r.text)}")),
        TestCase("3.3", "查询饮食记录", m["3.3"][lang], needs_pet=True,
                 setup=m["2.1"][lang],
                 check=lambda r, c: (bool(r.text.strip()), f"text_len={len(r.text)}")),

        # === Section 5: Pet Management ===
        TestCase("5.1", "创建宠物", m["5.1"][lang], no_pet=True,
                 check=lambda r, c: (r.has_card("pet_created"), f"cards={[x.get('type') for x in r.cards]}")),
        TestCase("5.4", "更新体重", m["5.4"][lang],
                 setup=m["5.1"][lang],  # create pet first
                 check=lambda r, c: (r.has_card("pet_updated") or r.has_card("confirm_action") or bool(r.text.strip()), f"cards={[x.get('type') for x in r.cards]}")),
        TestCase("5.9", "删除宠物", m["5.9"][lang],
                 setup=m["5.1"][lang],
                 check=lambda r, c: (r.has_card("confirm_action"), f"cards={[x.get('type') for x in r.cards]}")),

        # === Section 8: Reminders ===
        TestCase("8.1", "创建提醒", m["8.1"][lang], needs_pet=True,
                 check=lambda r, c: (r.has_card("reminder") or r.has_card("record") or r.has_card("confirm_action"), f"cards={[x.get('type') for x in r.cards]}")),
        TestCase("8.3", "列出提醒", m["8.3"][lang], needs_pet=True,
                 setup=m["8.1"][lang],
                 check=lambda r, c: (bool(r.text.strip()), f"text_len={len(r.text)}")),

        # === Section 9: Search Places ===
        TestCase("9.1", "搜索宠物医院", m["9.1"][lang], needs_pet=True,
                 location=ottawa_loc,
                 check=lambda r, c: (r.has_card("map") or r.has_card("places") or bool(r.text.strip()), f"cards={[x.get('type') for x in r.cards]}")),

        # === Section 10: Email ===
        TestCase("10.1", "草拟邮件", m["10.1"][lang], needs_pet=True,
                 check=lambda r, c: (r.has_card("email") or r.has_card("confirm_action"), f"cards={[x.get('type') for x in r.cards]}")),

        # === Section 11: Emergency ===
        TestCase("11.1", "紧急-抽搐", m["11.1"][lang], needs_pet=True,
                 check=lambda r, c: (r.emergency is not None, f"emergency={r.emergency}")),
        TestCase("11.2", "紧急-中毒", m["11.2"][lang], needs_pet=True,
                 check=lambda r, c: (r.emergency is not None, f"emergency={r.emergency}")),
        TestCase("11.3", "紧急误判排除", m["11.3"][lang], needs_pet=True,
                 check=lambda r, c: (r.emergency is None, f"emergency={r.emergency}, text={r.text[:60]}")),

        # === Section 12: Language Switch ===
        TestCase("12.1", "切换英文", m["12.1"][lang], needs_pet=True,
                 check=lambda r, c: (r.has_card("language") or bool(r.text.strip()), f"cards={[x.get('type') for x in r.cards]}")),
        TestCase("12.2", "切换中文", m["12.2"][lang], needs_pet=True,
                 check=lambda r, c: (r.has_card("language") or bool(r.text.strip()), f"cards={[x.get('type') for x in r.cards]}")),

        # === Section 13: Multi-pet ===
        TestCase("13.2", "两只宠物一起散步", m["13.2"][lang], needs_two_pets=True,
                 check=lambda r, c: (r.has_card("record") or bool(r.text.strip()), f"cards={[x.get('type') for x in r.cards]}")),
        TestCase("13.3", "单宠物自动关联", m["13.3"][lang], needs_pet=True,
                 check=lambda r, c: (r.has_card("record"), f"cards={[x.get('type') for x in r.cards]}")),

        # === Section 14: Profile ===
        TestCase("14.1", "性格描述", m["14.1"][lang], needs_pet=True,
                 check=lambda r, c: (bool(r.text.strip()), f"text_len={len(r.text)}")),
        TestCase("14.2", "总结档案", m["14.2"][lang], needs_pet=True,
                 check=lambda r, c: (bool(r.text.strip()), f"text_len={len(r.text)}")),

        # === Section 20: Edge Cases ===
        TestCase("20.1", "无宠物闲聊", m["20.1"][lang], no_pet=True,
                 check=lambda r, c: (bool(r.text.strip()), f"text_len={len(r.text)}")),
        TestCase("20.2", "有宠物无事件查询", m["20.2"][lang], needs_pet=True,
                 check=lambda r, c: (bool(r.text.strip()), f"text_len={len(r.text)}")),
        TestCase("20.4", "混合记录+提醒", m["20.4"][lang], needs_pet=True,
                 check=lambda r, c: (len(r.cards) >= 2, f"card_count={len(r.cards)}, types={[x.get('type') for x in r.cards]}")),
    ]
    return cases


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_single_case(case: TestCase, base_url: str, lang: str) -> dict:
    """Run a single test case and return full trace data."""
    client = E2EClient(base_url, debug=True)
    await client.auth_dev()

    # Setup: create pets if needed
    pet = None
    pets = []
    if case.needs_pet:
        pet = await client.create_pet("小维" if lang == "zh" else "Weiwei", "dog")
        pets = [pet]
    elif case.needs_two_pets:
        p1 = await client.create_pet("小维" if lang == "zh" else "Weiwei", "dog")
        p2 = await client.create_pet("花花" if lang == "zh" else "Huahua", "cat")
        pets = [p1, p2]

    # Setup message (if needed, e.g., create event before querying)
    setup_result = None
    if case.setup:
        setup_result = await client.chat(case.setup, location=case.location)

    # Run test message(s)
    if isinstance(case.message, list):
        # Sequence test
        results = []
        for msg in case.message:
            r = await client.chat(msg, location=case.location)
            results.append(r)
        result = results[-1]  # Check last result
        all_results = results
    else:
        result = await client.chat(case.message, location=case.location)
        all_results = [result]

    # Run check
    passed = False
    check_detail = ""
    if case.check:
        passed, check_detail = case.check(result, client)
    else:
        passed = True
        check_detail = "no check defined"

    # Collect API side effects
    side_effects = {}
    try:
        side_effects["pets"] = await client.get_pets()
    except Exception:
        pass
    try:
        side_effects["events_today"] = await client.get_events(date_str=today_str())
    except Exception:
        pass

    await client.close()

    return {
        "case_id": case.case_id,
        "name": case.name,
        "lang": lang,
        "message": case.message,
        "setup": case.setup,
        "passed": passed,
        "check_detail": check_detail,
        "result": {
            "text": result.text,
            "cards": result.cards,
            "emergency": result.emergency,
            "elapsed_ms": result.elapsed_ms,
            "error": result.error,
            "trace": result.trace,
        },
        "setup_result": {
            "text": setup_result.text if setup_result else None,
            "cards": setup_result.cards if setup_result else [],
            "elapsed_ms": setup_result.elapsed_ms if setup_result else 0,
        } if setup_result else None,
        "all_results": [{
            "text": r.text,
            "cards": r.cards,
            "elapsed_ms": r.elapsed_ms,
        } for r in all_results] if len(all_results) > 1 else None,
        "side_effects": side_effects,
    }


# ---------------------------------------------------------------------------
# Report Generator
# ---------------------------------------------------------------------------

def generate_report(results: list[dict], lang: str) -> str:
    """Generate markdown audit report from test results."""
    lines = []
    today = date.today().isoformat()

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    total_tokens = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_elapsed = 0
    total_llm_calls = 0

    for r in results:
        trace = r["result"].get("trace") or {}
        total_prompt_tokens += trace.get("total_prompt_tokens", 0)
        total_completion_tokens += trace.get("total_completion_tokens", 0)
        total_tokens += trace.get("total_tokens", 0)
        total_elapsed += r["result"]["elapsed_ms"]
        total_llm_calls += len(trace.get("llm_rounds", []))

    lines.append(f"# CozyPup E2E Audit Report")
    lines.append(f"")
    lines.append(f"> Generated: {today}")
    lines.append(f"> Language: {lang}")
    lines.append(f"> Total cases: {total} | ✅ Pass: {passed} | ❌ Fail: {failed}")
    lines.append(f"> Total time: {total_elapsed/1000:.1f}s | LLM calls: {total_llm_calls}")
    lines.append(f"> Tokens: prompt={total_prompt_tokens:,} completion={total_completion_tokens:,} total={total_tokens:,}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # Summary table
    lines.append(f"## Summary")
    lines.append(f"")
    lines.append(f"| # | Case | Status | Time | Tokens | Detail |")
    lines.append(f"|---|------|--------|------|--------|--------|")
    for r in results:
        trace = r["result"].get("trace") or {}
        tok = trace.get("total_tokens", 0)
        status = "✅" if r["passed"] else "❌"
        lines.append(
            f"| {r['case_id']} | {r['name']} | {status} | "
            f"{r['result']['elapsed_ms']}ms | {tok} | {r['check_detail'][:50]} |"
        )
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # Detailed results
    for r in results:
        _append_case_detail(lines, r)

    return "\n".join(lines)


def _append_case_detail(lines: list[str], r: dict):
    """Append detailed section for one test case."""
    status = "✅ PASS" if r["passed"] else "❌ FAIL"
    lines.append(f"## Test {r['case_id']}: {r['name']} — {status}")
    lines.append(f"")

    # Meta
    trace = r["result"].get("trace") or {}
    lines.append(f"### Meta")
    lines.append(f"- **Message**: `{_fmt_msg(r['message'])}`")
    if r["setup"]:
        lines.append(f"- **Setup message**: `{r['setup']}`")
    lines.append(f"- **Elapsed**: {r['result']['elapsed_ms']}ms")
    lines.append(f"- **Tokens**: prompt={trace.get('total_prompt_tokens', '?')} completion={trace.get('total_completion_tokens', '?')} total={trace.get('total_tokens', '?')}")
    lines.append(f"- **Check**: {r['check_detail']}")
    if r["result"]["error"]:
        lines.append(f"- **Error**: {r['result']['error']}")
    lines.append(f"")

    # Pipeline steps
    steps = trace.get("steps", [])
    if steps:
        lines.append(f"### Pipeline Trace")
        lines.append(f"")
        for s in steps:
            data = s.get("data", "")
            # Truncate long system prompts
            if s["step"] == "system_prompt" and isinstance(data, dict):
                data = {**data, "content": data.get("content", "")[:200] + "..."}
            data_str = json.dumps(data, ensure_ascii=False, default=str) if not isinstance(data, str) else data
            if len(data_str) > 300:
                data_str = data_str[:300] + "..."
            lines.append(f"- **{s['step']}** ({s['elapsed_ms']}ms): {data_str}")
        lines.append(f"")

    # LLM Rounds — FULL raw response JSON
    llm_rounds = trace.get("llm_rounds", [])
    for lr in llm_rounds:
        lines.append(f"### LLM Round {lr['round']} — Raw Response ({lr['elapsed_ms']}ms)")
        lines.append(f"")
        lines.append(f"```json")
        lines.append(json.dumps(lr["response"], ensure_ascii=False, indent=2, default=str))
        lines.append(f"```")
        lines.append(f"")

    # Final result
    lines.append(f"### Final Result")
    lines.append(f"- **Response text**: {r['result']['text'][:500]}")
    if r["result"]["cards"]:
        lines.append(f"- **Cards** ({len(r['result']['cards'])}):")
        for i, card in enumerate(r["result"]["cards"]):
            lines.append(f"  - [{i}] `{json.dumps(card, ensure_ascii=False, default=str)[:200]}`")
    if r["result"]["emergency"]:
        lines.append(f"- **Emergency**: `{json.dumps(r['result']['emergency'], ensure_ascii=False)}`")
    lines.append(f"")

    # Setup result if exists
    if r.get("setup_result") and r["setup_result"]["text"]:
        lines.append(f"### Setup Result")
        lines.append(f"- **Text**: {r['setup_result']['text'][:200]}")
        lines.append(f"- **Cards**: {r['setup_result']['cards']}")
        lines.append(f"")

    # Sequence results if exists
    if r.get("all_results"):
        lines.append(f"### Sequence Results ({len(r['all_results'])} messages)")
        for i, sr in enumerate(r["all_results"]):
            lines.append(f"- [{i}] ({sr['elapsed_ms']}ms) text={sr['text'][:100]}... cards={sr['cards']}")
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"")


def _fmt_msg(msg):
    if isinstance(msg, list):
        return " → ".join(msg)
    return msg


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="CozyPup E2E Audit Runner")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--lang", default="zh", choices=["zh", "en"])
    parser.add_argument("--case", default=None, help="Run specific case ID only (e.g. 2.1)")
    args = parser.parse_args()

    print(f"🔍 CozyPup E2E Audit — {args.lang} — {args.base_url}")
    print(f"")

    cases = build_test_cases(args.lang)
    if args.case:
        cases = [c for c in cases if c.case_id == args.case]
        if not cases:
            print(f"❌ Case {args.case} not found")
            return

    results = []
    for i, case in enumerate(cases):
        msg_preview = _fmt_msg(case.message)[:40]
        print(f"  [{i+1}/{len(cases)}] {case.case_id} {case.name}: {msg_preview}...", end=" ", flush=True)

        start = time.monotonic()
        try:
            r = await run_single_case(case, args.base_url, args.lang)
            results.append(r)
            elapsed = time.monotonic() - start
            status = "✅" if r["passed"] else "❌"
            trace = r["result"].get("trace") or {}
            tokens = trace.get("total_tokens", "?")
            print(f"{status} {elapsed:.1f}s tokens={tokens}")
        except Exception as exc:
            elapsed = time.monotonic() - start
            print(f"💥 {elapsed:.1f}s ERROR: {exc}")
            results.append({
                "case_id": case.case_id,
                "name": case.name,
                "lang": args.lang,
                "message": case.message,
                "setup": case.setup,
                "passed": False,
                "check_detail": f"EXCEPTION: {exc}",
                "result": {"text": "", "cards": [], "emergency": None,
                           "elapsed_ms": int(elapsed*1000), "error": str(exc), "trace": None},
                "setup_result": None,
                "all_results": None,
                "side_effects": {},
            })

    # Generate report — single case goes to separate file to avoid overwriting full runs
    report = generate_report(results, args.lang)
    report_dir = Path(__file__).parent / "reports"
    report_dir.mkdir(exist_ok=True)
    if args.case:
        suffix = f"-case-{args.case}"
    else:
        suffix = ""
    report_path = report_dir / f"audit-{date.today().isoformat()}-{args.lang}{suffix}.md"
    report_path.write_text(report, encoding="utf-8")

    # Also save raw JSON for programmatic analysis
    json_path = report_dir / f"audit-{date.today().isoformat()}-{args.lang}{suffix}.json"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"\n📄 Report: {report_path}")
    print(f"📊 Raw data: {json_path}")

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed")


if __name__ == "__main__":
    asyncio.run(main())
