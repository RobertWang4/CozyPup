# CozyPup Agent: 一条消息的完整旅程

`POST /api/v1/chat` 收到一句话之后发生的事，按代码顺序。
Agent loop 自 2026-09 起跑在 LangGraph 上（`app/agents/graph.py`），
不再是手写的 `while` 循环；节点调用 `loop.py` 里的共享 helper，
所以行为等价，但多出了 checkpoint、可恢复的 `interrupt`，和显式的状态机。

---

## 1. iOS 端（3 个文件）

| 文件 | 做什么 |
|---|---|
| `ChatView.swift` | 用户点发送，调 `ChatStore.sendMessage()` |
| `ChatStore.swift` | 乐观 UI 先追加用户消息，再调 `ChatService.streamChat()` |
| `ChatService.swift` | 构建 `ChatRequest`（message / session_id / location / language / images），经 `APIClient.streamRequest()` 打开 SSE 长连接，逐行解析 `event:` / `data:`，yield `SSEEvent` 枚举 |

`APIClient` 是个 Swift actor，负责 JWT；SSE 流在创建 async stream 之前同步取走 token。

---

## 2. 后端：请求进入 FastAPI

### `routers/chat.py` — `POST /api/v1/chat`

- `auth.py:get_current_user_id` 从 JWT 取 `user_id`
- `X-Debug: true` → 创建 `TraceCollector`（否则用 `INACTIVE_TRACE` 哨兵，零开销）
- 返回 `EventSourceResponse(_event_generator(...))`

`_event_generator()` 在图启动前做四件事：

**Phase 0 — 会话与消息落库**
```
_get_or_create_session()   每用户每天一个 session
_save_message()            用户消息立即存 DB（不等图片）
_save_images_to_disk()     图片在线程池里写磁盘，不阻塞
```

**Phase 1 — 预处理（正则部分纯同步，毫秒级）**
```
locale.detect_language()          CJK 字符检测 → zh / en
emergency.detect_emergency()      紧急关键词正则
emergency_clf.classify()          微调 Qwen3-0.6B 侧车，create_task 与下面并行（见 §5）
pre_processing.pre_process()       → SuggestedAction(工具名, 参数, 置信度)
_get_recent_messages() / _get_pets()
```

**Phase 2 — 组装 prompt（`chat_turn.build_agent_prompt_input`）**

先 `await memory.build_memory_context()`（pgvector 检索用户记忆 + 全局知识库，
带超时保护），渲染成 Markdown 片段，再交给 `prompts_v2.build_system_prompt`。

按 静态 → 半静态 → 动态 排列，最大化 provider 端前缀缓存命中：

```
base_system_prompt + tool_decision_tree   静态，100% 前缀缓存
宠物档案 pet.profile_md                    半静态
session.context_summary                    偶尔变
memory context / 紧急提示 / 预处理建议      动态
今天日期
```

**模型选择**：紧急 → `settings.emergency_model`（默认 `openai/gpt-5`，可配独立
API base/key），日常 → `settings.model`（默认 `deepseek/deepseek-flash`）。注入了
图片的那一轮切 `settings.vision_model`。

**Phase 3 — 跑图**，`stream_agent()` 产出 `("sse", {event, data})`，最后一项固定是
`("result", OrchestratorResult)`。`chat.py` 把它们序列化成 SSE 帧。

---

## 3. 图（`app/agents/graph.py`）

六个节点，状态是一个 `AgentState` TypedDict。

```
START → prepare → model ──tool_calls──→ tools ──→ model
                    │                     │
                    │ no tool_calls       ├──deferred──→ confirm ⇄ confirm
                    ↓                     │                 │
                  review ──retry──→ model └──skip/cap──→ finalize → END
                    └──deferred──→ confirm
```

| 节点 | 职责 |
|---|---|
| `prepare` | seed messages、pushback 前导语（`_detect_pushback`） |
| `model` | `micro_compact` 压掉旧 tool result、按需切 vision model、`_stream_completion` 流式调用；`round` 在这里 +1 |
| `tools` | 每个 tool_call 走 `dispatch_tool`；注入图片；算 `skip_round2`；需要用户确认的调用**不执行**，而是塞一条 `waiting_confirm` tool message |
| `confirm` | 对一个被延后的调用 `interrupt()`；恢复后执行它 |
| `review` | plan nag → write-claim nag → nudge |
| `finalize` | 拼文本、编造行为守卫（`_text_claims_write`）、空回复兜底 |

关键约束都在 `MAX_ROUNDS`（默认 5）上：两条回边都检查轮数上限。

### 状态设计

`messages` / `text_parts` / `cards` / `prompt_tokens` 用 reducer（`add`、集合并集）
声明，节点只返回自己的增量，不做覆盖式写入。`deferred_confirms` 故意**不带**
reducer——`confirm` 要从队首弹出。

不可序列化的 per-request 上下文（`db` session、`TraceCollector`、模型名、base64
图片）走 `config["configurable"]`，不进 state：checkpoint 必须能 JSON 往返。

### 流式输出

节点内部用 `get_stream_writer()` 推 `{"event": ..., "data": ...}`。token、thinking
气泡、card 都是这条路。`stream_agent` 以 `stream_mode=["custom", "updates"]` 消费。

---

## 4. 确认门控 = `interrupt` + Postgres checkpointer

破坏性工具（`delete_pet`、`delete_calendar_event` 等，集合在
`agents/constants.py:CONFIRM_TOOLS`）不由 LLM 决定是否落库：

1. `tools` 节点把这个调用参数原样记进 `deferred_confirms`，并给它的
   `tool_call_id` 回一条 `waiting_confirm`——每个 tool_call 必须有回复，
   而且这样模型还能看到**同一轮里其他工具的真实结果**，把话说完整。
2. 一轮结束、本来要 `finalize` 的时候才进 `confirm` 节点 `interrupt()`。
   所以确认卡永远是这个 turn 的最后一个 SSE 事件，`finalize` 每 turn 只跑一次。
3. `interrupt()` 把整个图状态写进 checkpoint。thread id 是
   `"<user_id>:<correlation_id>"`，作为 `action_id` 放在卡片里发给 iOS。
4. 用户点确认 → `POST /chat/confirm-action` → 用那个 thread id
   `Command(resume=True)` 恢复，执行**预存的参数**，不再问 LLM，
   所以"LLM 改口"不可能发生。恢复后直接进 `finalize`（不再多跑一轮 LLM：
   为一句用户看不见的话把确认从 ~200ms 变成 ~5s 不值得）；只有工具报错才回 `model`。

`app/agents/checkpointer.py`：一个进程一个 `AsyncPostgresSaver`，跑在一个小
`AsyncConnectionPool` 上，连的是 SQLAlchemy 用的同一个库。两个细节值得一提：

- **序列化器会抹掉图片**。`RedactingSerializer` 在写入时把 `data:image/...`
  的 base64 换成占位符——`request_images` 会往消息里塞完整 data URI，
  照原样 checkpoint 就是几 MB。恢复时不再调模型，所以这些字节不需要留。
- **启动失败不阻塞 boot**。`setup()` 建表失败只记日志，图退化成
  `InMemorySaver`，聊天照常，只有 `/chat/confirm-action` 开始返 503。
  checkpoint 只为恢复一次 interrupt 而存在，所以又小又短命：
  `prune_checkpoints()`（挂在 `admin ops checkpoints prune`）按时间清掉整个 thread。

### 迁移结果

harness（`app/agent_harness/`，见 §6）在每个阶段上线前后各跑一遍同一组场景。
`pass^2` = 同一场景重复跑两次都通过的比例，用来把模型抖动和真实回归分开：

| 阶段 | pass^2 | 平均 tokens | 轮数 | 耗时 |
|---|---|---|---|---|
| 迁移前基线 | 83% | 27.2k | 2.2 | 11.3s |
| 阶段 1（图替换循环） | 89% | 26.8k | 2.1 | 10.2s |
| 阶段 2a（状态可序列化） | 83% | 26.1k | 2.1 | 10.0s |
| 阶段 2b（Postgres checkpointer + interrupt） | 94% | 26.7k | 2.1 | 10.9s |

阶段 2a 回到基线是因为三处序列化改造（`messages` 换 `add` reducer、`pets` 转
dict、base64 图片移出 state）只求等价不求提升；10 个新单测钉住每轮送给 LLM 的
message list 与阶段 1 逐字节一致。剩下的唯一失败项
（`zh_statement_needs_confirm`）与基线相同：模型在卡片还没确认时就声称"已记下"，
是 prompt 层问题，不是图逻辑问题。

---

## 5. 紧急路由

```
"我的狗在抽搐！"
  ├─ emergency.py           正则命中 "抽搐" → EmergencyCheckResult(detected=True)
  ├─ emergency_clf.py       侧车 llama-server 一次前向，读 true/false 两个 token
  │                         的 logprob 做 softmax → P(true)
  ├─ emergency_clf.resolve() 按 emergency_clf_mode flag 合并两方结论：
  │                         off / shadow（只记日志）/ union（或）/ clf（模型为主）
  ├─ 命中 → 换 settings.emergency_model
  └─ prompt 注入提示，由 LLM 做最终判断：
      真紧急   → trigger_emergency(action="find_er") → SSE emergency 事件
      假警报   → 正常文字回复（"上次抽搐是什么时候"不该触发）
```

正则只做便宜的预筛，LLM 做最终判断，所以纯关键词那种误报不会流到用户面前。
每一轮都写一条 `emergency_clf` trace，两方不一致时带 `disagree=true`——
这些分歧导出来人工看过，就是下一轮训练集。分类器细节见
[`../backend/nano/README.md`](../backend/nano/README.md)。

---

## 6. 三层容错

| 层 | 代码 | 作用 |
|---|---|---|
| 预处理器 | `pre_processing/` | 正则提意图 → 带置信度的 `SuggestedAction`，作为提示注入 prompt |
| 校验 → 自修复 | `validation.py` | `validate_tool_args()` 返回错误列表（不抛异常），错误作为 tool result 喂回，LLM 下一轮自己改参数重试 |
| Nudge / nag | `review` 节点 | 高置信度工具没调 → 注入催促重跑一轮；plan 步骤没做完 → plan nag；文本声称写了但没调写工具 → write-claim nag。每种各一次 |

外加 `finalize` 的编造行为守卫和空回复兜底。这三层就是"用便宜模型也能可靠"
的全部秘密——没有一处依赖模型自觉。

---

## 7. Phase 4：收尾（不阻塞 SSE）

```
profile_extractor.merge_into_profile_md()   并行 LLM 提取的宠物信息合并进 profile_md
memory.event_sync                            日历事件 ↔ behavioral 记忆节点同步
_save_message(assistant)                     完整回复 + 所有卡片 JSON 存库
context_agent.trigger_summary_if_needed()    未摘要消息 ≥5 条 → 后台压缩成结构化摘要

yield "event: __debug__"    仅 X-Debug: true
yield "event: done"         iOS 收到后停 loading
```

---

## 8. 回到 iOS 端

| SSE 事件 | iOS 处理 |
|---|---|
| `event: token` | 逐字追加到 AI 消息气泡 |
| `event: thinking` | 工具执行中的思考气泡 |
| `event: card` | 解码成 `CardData`，追加到同一条消息下方 |
| `event: emergency` | 红色紧急横幅 + 急救指导 |
| `event: done` | 停 loading，保存 session_id |

卡片是 append 到同一条消息、渲染位置固定在文本下方，所以不受 SSE 顺序影响
——这就是确认卡可以安全地排在 turn 最后的前提。

---

## 9. 一条消息经过的文件清单

| # | 文件 | 关键函数 |
|---|---|---|
| 1 | `ios-app/.../ChatView.swift` | 发送按钮 |
| 2 | `ios-app/.../ChatStore.swift` | `sendMessage()` |
| 3 | `ios-app/.../ChatService.swift` | `streamChat()` |
| 4 | `ios-app/.../APIClient.swift` | `streamRequest()` |
| 5 | `backend/app/routers/chat.py` | `chat()` → `_event_generator()` |
| 6 | `backend/app/agents/locale.py` | `detect_language()` |
| 7 | `backend/app/agents/emergency.py` | `detect_emergency()` |
| 8 | `backend/app/agents/emergency_clf.py` | `classify()` / `resolve()` |
| 9 | `backend/app/agents/pre_processing/` | `pre_process()` |
| 10 | `backend/app/agents/chat_turn.py` | `build_agent_prompt_input()` |
| 11 | `backend/app/memory/context_builder.py` | `build_memory_context()` |
| 12 | `backend/app/agents/prompts_v2.py` | `build_system_prompt()` |
| 13 | `backend/app/agents/graph.py` | `stream_agent()` + 六个节点 |
| 14 | `backend/app/agents/checkpointer.py` | `AsyncPostgresSaver` + `RedactingSerializer` |
| 15 | `backend/app/agents/loop.py` | `dispatch_tool()`、`stream_completion()` |
| 16 | `backend/app/agents/validation.py` | `validate_tool_args()` |
| 17 | `backend/app/agents/tools/registry.py` | `execute_tool()` |
| 18 | `backend/app/agents/context_agent.py` | `trigger_summary_if_needed()` |
| 19 | `backend/app/agents/profile_extractor.py` | `extract_profile_info()` |
