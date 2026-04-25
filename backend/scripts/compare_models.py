#!/usr/bin/env python3
"""
Model comparison script — Grok 4.1 Fast vs DeepSeek V4 Flash

Usage:
    cd backend && python scripts/compare_models.py              # Grok vs Ollama local
    cd backend && python scripts/compare_models.py --deepseek   # Grok vs DeepSeek official
    cd backend && python scripts/compare_models.py --ollama     # Grok vs Ollama local

Prerequisites:
    - Grok key already configured in .env (MODEL_API_KEY)
    - For --deepseek: set DEEPSEEK_API_KEY in .env (get from platform.deepseek.com)
    - For --ollama: ensure ollama is running with deepseek-v4-flash:cloud pulled
"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import litellm

from app.agents.tools import TOOL_DEFINITIONS
from app.config import settings


# ---------------------------------------------------------------------------
# Load configs from .env
# ---------------------------------------------------------------------------

def load_env():
    """Load .env file into os.environ."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())


load_env()

# Grok config (from active MODEL_* vars)
GROK_MODEL = settings.model
GROK_BASE = settings.model_api_base or os.getenv("MODEL_API_BASE", "")
GROK_KEY = settings.model_api_key or os.getenv("MODEL_API_KEY", "")

# DeepSeek official config
DS_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-v4-flash")
DS_EMERGENCY = os.getenv("DEEPSEEK_EMERGENCY_MODEL", "deepseek/deepseek-v4-pro")
DS_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DS_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# Ollama local config
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "ollama/deepseek-v4-flash:cloud")
OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://localhost:11434")


# ---------------------------------------------------------------------------
# Test cases (selected representative samples)
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    name: str
    user_msg: str
    expected_tools: list[str]
    system_ctx: dict = field(default_factory=dict)
    description: str = ""


TODAY = date.today().isoformat()

TEST_CASES = [
    TestCase(
        name="2.1 记录饮食",
        user_msg="小维今天吃了狗粮",
        expected_tools=["create_calendar_event"],
        system_ctx={"pets": [{"id": "pet-weiwei", "name": "小维", "species": "dog"}]},
        description="基础工具调用：饮食记录 → create_calendar_event(category=diet)",
    ),
    TestCase(
        name="2.6 异常事件",
        user_msg="小维吐了",
        expected_tools=["create_calendar_event"],
        system_ctx={"pets": [{"id": "pet-weiwei", "name": "小维", "species": "dog"}]},
        description="异常事件：呕吐 → create_calendar_event(category=abnormal)",
    ),
    TestCase(
        name="12.1 紧急情况",
        user_msg="我的猫突然抽搐了！",
        expected_tools=["trigger_emergency"],
        system_ctx={"pets": []},
        description="紧急情况：抽搐 → trigger_emergency",
    ),
    TestCase(
        name="16.1 RAG问答",
        user_msg="小维呕吐了怎么办",
        expected_tools=["search_knowledge"],
        system_ctx={"pets": [{"id": "pet-weiwei", "name": "小维", "species": "dog"}]},
        description="健康问答：呕吐怎么办 → search_knowledge",
    ),
    TestCase(
        name="38.1 无工具闲聊",
        user_msg="今天天气真好",
        expected_tools=[],
        system_ctx={"pets": [{"id": "pet-weiwei", "name": "小维", "species": "dog"}]},
        description="幻觉防御：闲聊天气 → 不应该调用任何工具",
    ),
    TestCase(
        name="40.1 双任务",
        user_msg="记录小维今天吃了狗粮，提醒我明天打疫苗",
        expected_tools=["plan"],
        system_ctx={"pets": [{"id": "pet-weiwei", "name": "小维", "species": "dog"}]},
        description="多任务：饮食记录 + 提醒 → plan tool",
    ),
    TestCase(
        name="5.1 新建宠物",
        user_msg="我新养了一只猫叫花花",
        expected_tools=["create_pet"],
        system_ctx={"pets": []},
        description="宠物创建：新猫 → create_pet",
    ),
    TestCase(
        name="38.7 历史查询(不应触发紧急)",
        user_msg="小维上次中毒是什么时候",
        expected_tools=["query_calendar_events"],
        system_ctx={"pets": [{"id": "pet-weiwei", "name": "小维", "species": "dog"}]},
        description="历史查询：上次中毒 → query_calendar_events",
    ),
    TestCase(
        name="40.7 三任务",
        user_msg="记录今天散步、提醒明天打疫苗、创建每天喂药的待办",
        expected_tools=["plan"],
        system_ctx={"pets": [{"id": "pet-weiwei", "name": "小维", "species": "dog"}]},
        description="复杂多任务：记录 + 提醒 + 待办 → plan tool",
    ),
    TestCase(
        name="8.1 每日待办",
        user_msg="每天提醒我遛狗",
        expected_tools=["create_daily_task"],
        system_ctx={"pets": [{"id": "pet-weiwei", "name": "小维", "species": "dog"}]},
        description="待办创建：每天遛狗 → create_daily_task",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_system_prompt(ctx: dict) -> str:
    pets = ctx.get("pets", [])
    if pets:
        lines = [f"- {p['name']} ({p['species']}, id={p['id']})" for p in pets]
        pet_info = "当前宠物:\n" + "\n".join(lines) + "\n"
    else:
        pet_info = "当前还没有宠物。\n"
    return (
        "你是 CozyPup 的 AI 助手，一个智能宠物健康助理。"
        "你的任务是根据用户的自然语言指令，调用适当的工具来完成操作。"
        "不要编造不存在的信息，不要调用不必要的工具。\n\n"
        f"今天是 {TODAY}。\n"
        f"{pet_info}"
        "如果用户提到宠物但没有明确名字，且当前只有一只宠物，就默认用那只。"
    )


def extract_tool_calls(response) -> list[dict]:
    calls = []
    if not response or not response.choices:
        return calls
    msg = response.choices[0].message
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        for tc in msg.tool_calls:
            calls.append({"name": tc.function.name, "arguments": tc.function.arguments})
    elif hasattr(msg, "function_call") and msg.function_call:
        fc = msg.function_call
        calls.append({"name": fc.name, "arguments": fc.arguments})
    return calls


def check_hallucinations(calls: list[dict], expected: list[str]) -> list[str]:
    issues = []
    actual_names = [c["name"] for c in calls]

    for name in actual_names:
        if name not in expected:
            issues.append(f"幻觉工具: {name} (不在预期 {expected} 中)")
    for name in expected:
        if name not in actual_names:
            issues.append(f"漏调工具: {name} (预期应调用)")

    known_params = {
        "create_calendar_event": {"event_date", "title", "category", "pet_id", "pet_ids", "cost", "reminder_at", "notes", "event_time", "raw_text"},
        "create_pet": {"name", "species", "breed", "birthday", "weight_kg", "gender", "profile_md"},
        "create_reminder": {"pet_id", "title", "type", "trigger_at", "notes"},
        "create_daily_task": {"title", "pet_id", "type", "frequency", "start_date", "end_date", "time_of_day", "days_of_week", "daily_target"},
        "trigger_emergency": {"message", "action"},
        "query_calendar_events": {"pet_id", "start_date", "end_date", "category"},
        "search_knowledge": {"query", "pet_id", "species"},
        "plan": {"steps"},
    }
    for call in calls:
        name = call["name"]
        try:
            args = json.loads(call["arguments"]) if isinstance(call["arguments"], str) else call["arguments"]
        except json.JSONDecodeError:
            issues.append(f"参数解析失败: {name}")
            continue
        if not isinstance(args, dict):
            issues.append(f"参数格式错误: {name} - 不是 dict")
            continue
        extra = set(args.keys()) - known_params.get(name, set())
        if extra:
            issues.append(f"幻觉参数: {name} 包含未定义参数 {extra}")
    return issues


async def call_model(model: str, base: str, key: str | None, messages: list, tools: list | None) -> dict:
    kw = {}
    if base:
        kw["api_base"] = base
    if key:
        kw["api_key"] = key

    start = asyncio.get_event_loop().time()
    try:
        response = await litellm.acompletion(
            model=model, messages=messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
            temperature=0.1, timeout=60, **kw,
        )
        elapsed = asyncio.get_event_loop().time() - start
        calls = extract_tool_calls(response)
        text = response.choices[0].message.content or "" if response.choices else ""
        return {"ok": True, "text": text, "tool_calls": calls, "elapsed_ms": int(elapsed * 1000), "raw_model": model}
    except Exception as exc:
        elapsed = asyncio.get_event_loop().time() - start
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "elapsed_ms": int(elapsed * 1000), "raw_model": model}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_comparison(use_deepseek: bool = False, use_ollama: bool = False):
    if use_deepseek:
        ds_label = "DeepSeek Official"
        ds_model = DS_MODEL
        ds_base = DS_BASE
        ds_key = DS_KEY
        if not ds_key or ds_key == "your-deepseek-api-key-here":
            print("=" * 70)
            print("❌  DeepSeek API Key 未配置")
            print("=" * 70)
            print()
            print("请按以下步骤获取 API Key 并配置：")
            print()
            print("  1. 访问 https://platform.deepseek.com/ 注册/登录")
            print("  2. 进入 API Keys 页面，创建新 Key")
            print("  3. 编辑 backend/.env，将 DEEPSEEK_API_KEY 的值替换为你的真实 Key：")
            print()
            print("     DEEPSEEK_API_KEY=sk-xxxxxxxx")
            print()
            print("  4. 重新运行本脚本")
            print()
            return []
    elif use_ollama:
        ds_label = "Ollama Local"
        ds_model = OLLAMA_MODEL
        ds_base = OLLAMA_BASE
        ds_key = ""
    else:
        ds_label = "Ollama Local"
        ds_model = OLLAMA_MODEL
        ds_base = OLLAMA_BASE
        ds_key = ""

    print(f"=" * 70)
    print(f"模型对比：Grok 4.1 Fast vs {ds_label}")
    print(f"=" * 70)
    print(f"Grok:    {GROK_MODEL}")
    print(f"         base={GROK_BASE[:40]}...")
    print(f"{ds_label}: {ds_model}")
    print(f"         base={ds_base}")
    print(f"=" * 70)

    results = []

    for tc in TEST_CASES:
        print(f"\n{'─' * 70}")
        print(f"测试: {tc.name}")
        print(f"输入: {tc.user_msg}")
        print(f"预期工具: {tc.expected_tools or '(无)'}")

        sys_prompt = build_system_prompt(tc.system_ctx)
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": tc.user_msg},
        ]

        grok_task = call_model(GROK_MODEL, GROK_BASE, GROK_KEY, messages, TOOL_DEFINITIONS)
        ds_task = call_model(ds_model, ds_base, ds_key, messages, TOOL_DEFINITIONS)
        grok_res, ds_res = await asyncio.gather(grok_task, ds_task)

        grok_tools = [c["name"] for c in grok_res.get("tool_calls", [])]
        ds_tools = [c["name"] for c in ds_res.get("tool_calls", [])]
        grok_issues = check_hallucinations(grok_res.get("tool_calls", []), tc.expected_tools) if grok_res.get("ok") else [f"调用失败: {grok_res.get('error')}"]
        ds_issues = check_hallucinations(ds_res.get("tool_calls", []), tc.expected_tools) if ds_res.get("ok") else [f"调用失败: {ds_res.get('error')}"]

        results.append({"case": tc, "grok": grok_res, "deepseek": ds_res,
                        "grok_issues": grok_issues, "deepseek_issues": ds_issues})

        print(f"\n  Grok ({grok_res.get('elapsed_ms', 0)}ms):")
        if grok_res.get("ok"):
            print(f"    工具调用: {grok_tools or '(无)'}")
            if grok_issues:
                for issue in grok_issues:
                    print(f"    ❌ {issue}")
            else:
                print(f"    ✅ 无幻觉")
            if grok_res.get("text"):
                print(f"    回复: {grok_res['text'][:80]}...")
        else:
            print(f"    ❌ 失败: {grok_res.get('error')}")

        print(f"\n  {ds_label} ({ds_res.get('elapsed_ms', 0)}ms):")
        if ds_res.get("ok"):
            print(f"    工具调用: {ds_tools or '(无)'}")
            if ds_issues:
                for issue in ds_issues:
                    print(f"    ❌ {issue}")
            else:
                print(f"    ✅ 无幻觉")
            if ds_res.get("text"):
                print(f"    回复: {ds_res['text'][:80]}...")
        else:
            print(f"    ❌ 失败: {ds_res.get('error')}")

    # Summary
    print(f"\n{'=' * 70}")
    print("汇总报告")
    print(f"{'=' * 70}")

    grok_total = len([r for r in results if r["grok"].get("ok")])
    ds_total = len([r for r in results if r["deepseek"].get("ok")])
    grok_pass = len([r for r in results if r["grok"].get("ok") and not r["grok_issues"]])
    ds_pass = len([r for r in results if r["deepseek"].get("ok") and not r["deepseek_issues"]])
    grok_hallucinations = sum(len(r["grok_issues"]) for r in results if r["grok"].get("ok"))
    ds_hallucinations = sum(len(r["deepseek_issues"]) for r in results if r["deepseek"].get("ok"))

    avg_grok = sum(r["grok"]["elapsed_ms"] for r in results if r["grok"].get("ok")) // max(grok_total, 1)
    avg_ds = sum(r["deepseek"]["elapsed_ms"] for r in results if r["deepseek"].get("ok")) // max(ds_total, 1)

    print(f"\nGrok 4.1 Fast:")
    print(f"  成功调用: {grok_total}/{len(results)}")
    print(f"  无幻觉 case: {grok_pass}/{grok_total}")
    print(f"  幻觉/错误数: {grok_hallucinations}")
    print(f"  平均延迟: {avg_grok}ms")

    print(f"\n{ds_label}:")
    print(f"  成功调用: {ds_total}/{len(results)}")
    print(f"  无幻觉 case: {ds_pass}/{ds_total}")
    print(f"  幻觉/错误数: {ds_hallucinations}")
    print(f"  平均延迟: {avg_ds}ms")

    print(f"\n{'─' * 70}")
    print("详细问题列表")
    print(f"{'─' * 70}")
    for r in results:
        if r["grok_issues"] or r["deepseek_issues"]:
            print(f"\n{r['case'].name}: {r['case'].user_msg}")
            if r["grok_issues"]:
                print(f"  Grok: {r['grok_issues']}")
            if r["deepseek_issues"]:
                print(f"  {ds_label}: {r['deepseek_issues']}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare Grok vs DeepSeek tool calling accuracy")
    parser.add_argument("--deepseek", action="store_true", help="Compare against DeepSeek official API (requires DEEPSEEK_API_KEY in .env)")
    parser.add_argument("--ollama", action="store_true", help="Compare against local Ollama (default)")
    args = parser.parse_args()

    asyncio.run(run_comparison(use_deepseek=args.deepseek, use_ollama=args.ollama))
