"""
LangGraph 学习 demo — 一个迷你版的 CozyPup agent 循环。

运行：cd backend && .venv/bin/python scripts/langgraph_demo.py

不调真实 LLM：`fake_llm` 按脚本返回，所以你可以专注看"图"本身。
对照 docs/superpowers/specs/2026-09-03-langgraph-migration.md 的 §4 来读。

五个概念，按出现顺序：
  ① State + reducer      —— 节点返回"增量"，reducer 决定怎么合并进 state
  ② 节点 = 普通函数        —— 输入 state，返回 dict（只写自己改的字段）
  ③ 条件边               —— 一个函数看 state 决定下一步去哪个节点
  ④ get_stream_writer    —— 节点内推自定义事件（对应 SSE 的 token 事件）
  ⑤ interrupt / Command  —— 暂停图等用户确认，之后从断点恢复（对应确认卡）
"""

from operator import add
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


# ──────────────────────────────────────────────────────────────
# ① State
#
# Annotated[list, add] 的意思：节点返回 {"messages": [x]} 时，
# LangGraph 会做 state.messages + [x]，而不是覆盖。
# 没有 Annotated 的字段（round / done）就是直接覆盖。
# ──────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list[dict], add]      # OpenAI 格式的对话历史
    text_parts: Annotated[list[str], add]     # 模型输出的文本片段
    tools_executed: Annotated[list[str], add]
    round: int


# ──────────────────────────────────────────────────────────────
# 假 LLM：按 round 返回固定结果，模拟"先调工具，再总结"
# 真迁移时这里换成 litellm.acompletion(stream=True)
# ──────────────────────────────────────────────────────────────
def fake_llm(messages: list[dict], round_: int) -> dict:
    if round_ == 0:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "c1", "name": "get_pet", "args": {"name": "旺财"}},
                {"id": "c2", "name": "delete_event", "args": {"event_id": 42}},
            ],
        }
    return {"role": "assistant", "content": "旺财是柴犬，事件 42 已处理。"}


# ──────────────────────────────────────────────────────────────
# ② 节点：model
# ──────────────────────────────────────────────────────────────
def model_node(state: AgentState) -> dict:
    reply = fake_llm(state["messages"], state["round"])

    # ④ 自定义流：真实场景里这里是逐 token 推，chat.py 收到后转成 SSE `event: token`
    writer = get_stream_writer()
    for ch in reply["content"]:
        writer({"type": "token", "text": ch})

    return {
        "messages": [reply],                   # reducer 会 append
        "text_parts": [reply["content"]] if reply["content"] else [],
        "round": state["round"] + 1,           # 普通字段，覆盖
    }


# ──────────────────────────────────────────────────────────────
# ② 节点：tools
# ──────────────────────────────────────────────────────────────
DESTRUCTIVE = {"delete_event"}   # 对应 constants.py 的 CONFIRM_TOOLS


def tools_node(state: AgentState) -> dict:
    last = state["messages"][-1]
    new_msgs, executed = [], []

    for call in last["tool_calls"]:
        name, args = call["name"], call["args"]

        if name in DESTRUCTIVE:
            # ⑤ interrupt：图在这里"暂停"并把 payload 交给调用方（→ 确认卡）。
            #   调用方之后用 Command(resume=...) 恢复，interrupt() 就返回 resume 的值。
            #   注意：恢复时这个节点会从头重跑，所以节点里 interrupt 之前不要有副作用。
            approved = interrupt({"card": "confirm_action", "tool": name, "args": args})
            if not approved:
                new_msgs.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": "用户取消了操作"})
                continue

        # 这里对应现有的 dispatch_tool（guards → execute）
        result = f"{name}({args}) ok"
        executed.append(name)
        new_msgs.append({"role": "tool", "tool_call_id": call["id"], "content": result})

    return {"messages": new_msgs, "tools_executed": executed}


# ──────────────────────────────────────────────────────────────
# ③ 条件边：model 跑完后去哪
# ──────────────────────────────────────────────────────────────
MAX_ROUNDS = 5


def after_model(state: AgentState) -> str:
    last = state["messages"][-1]
    if last.get("tool_calls") and state["round"] < MAX_ROUNDS:
        return "tools"
    return END


# ──────────────────────────────────────────────────────────────
# 组图
#   START → model ─(有 tool_calls)→ tools → model → ... ─(没有)→ END
# ──────────────────────────────────────────────────────────────
builder = StateGraph(AgentState)
builder.add_node("model", model_node)
builder.add_node("tools", tools_node)
builder.add_edge(START, "model")
builder.add_conditional_edges("model", after_model, {"tools": "tools", END: END})
builder.add_edge("tools", "model")

# checkpointer 是 interrupt 的前提：暂停时要把 state 存下来，恢复时读回来。
# 生产上换成 AsyncPostgresSaver；thread_id 对应 CozyPup 的 session_id。
graph = builder.compile(checkpointer=InMemorySaver())


# ──────────────────────────────────────────────────────────────
# 驱动：模拟 chat.py 的两次 HTTP 请求
#   第一次 POST /chat            → 图跑到 interrupt 停下
#   第二次 POST /confirm-action  → Command(resume=True) 接着跑
# ──────────────────────────────────────────────────────────────
def run(inp, config):
    # stream_mode 选两种：custom = 节点里 writer 推的；updates = 每个节点返回的增量
    for mode, chunk in graph.stream(inp, config, stream_mode=["custom", "updates"]):
        if mode == "custom":
            print(f"  [token] {chunk['text']}")
        elif "__interrupt__" in chunk:
            print(f"  [interrupt] 发确认卡: {chunk['__interrupt__'][0].value}")
        else:
            node, delta = next(iter(chunk.items()))
            print(f"  [node:{node}] 返回增量 keys={list(delta)}")


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "session-2026-09-03"}}

    print("── 请求 1：用户发消息 ──")
    run(
        {"messages": [{"role": "user", "content": "旺财是什么品种？顺便删掉事件42"}],
         "round": 0},
        config,
    )

    print("\n── 图停住了。此时 state 已存在 checkpointer 里 ──")
    snap = graph.get_state(config)
    print(f"  next 节点 = {snap.next}, round = {snap.values['round']}")

    print("\n── 请求 2：用户点了确认卡 ──")
    run(Command(resume=True), config)

    print("\n── 最终 state ──")
    final = graph.get_state(config).values
    print("  text        =", "".join(final["text_parts"]))
    print("  executed    =", final["tools_executed"])
    print("  messages 数 =", len(final["messages"]))
