# CozyPup Agent: 一条消息的完整旅程

## iOS 端（3 个文件）

### 1. `ChatView.swift` — 用户点发送
用户在输入框输入文字，点击发送按钮，调用 `ChatStore.sendMessage()`。

### 2. `ChatStore.swift` — 管理消息状态
在 `messages` 数组里追加用户消息（乐观 UI），然后调用 `ChatService.streamChat()`。

### 3. `ChatService.swift:25` — 发起 SSE 请求
- 构建 `ChatRequest`（message, session_id, location, language, images）
- 调用 `APIClient.shared.streamRequest("/chat", body)`
- `APIClient.swift:189` 用 `URLSession.bytes` 打开 SSE 长连接
- 逐行解析 `event:` / `data:`，yield 出 `SSEEvent` 枚举（token / card / emergency / done）

---

## 后端（请求进入 FastAPI）

### 4. `routers/chat.py:537` — `POST /api/v1/chat` 入口
- JWT 认证 (`auth.py:get_current_user_id`) 提取 user_id
- 检查 `X-Debug` 请求头 → 决定是否创建 `TraceCollector`
- 返回 `EventSourceResponse(_event_generator(...))`

### 5. `routers/chat.py:233` — `_event_generator()` 主函数

整个聊天流程分为 4 个阶段：

#### Phase 0: 会话 & 消息保存
```
_get_or_create_session()  → 获取/创建当日 session（每用户每天一个）
_save_message()           → 用户消息立即存 DB（不等图片）
_save_images_to_disk()    → 图片在线程池里异步写磁盘（run_in_executor，不阻塞）
```

#### Phase 1: 并行预处理（3 个同步函数，毫秒级）
```
locale.py:detect_language()           → 正则检测中/英文（CJK 字符检测）
emergency.py:detect_emergency()       → 正则匹配紧急关键词（"中毒""抽搐"等）
pre_processing/:pre_process()         → 从文本提取 SuggestedAction（工具名+参数+置信度）
  ├─ calendar_detect.detect()         → 日历事件检测
  ├─ pet_detect.detect_create_pet()   → 创建宠物检测
  ├─ reminder_detect.detect()         → 提醒检测
  ├─ task_detect.detect()             → 每日任务检测
  ├─ misc_detect.detect()             → 杂项检测
  └─ pet_detect.detect_update_profile() → 更新档案检测
_get_recent_messages()                → 加载最近 5 条历史消息
_get_pets()                           → 加载用户所有宠物档案
```

#### Phase 2: 构建 Prompt
```
emergency.py:build_emergency_hint()   → 如果检测到紧急词，构建紧急提示
prompts_v2.py:build_system_prompt()   → 组装 system prompt（按缓存友好顺序）：
  ├─ base_system_prompt + tool_decision_tree    （静态，100% 前缀缓存命中）
  ├─ 宠物档案（半静态）
  ├─ 会话摘要 session.context_summary（偶尔变）
  ├─ 紧急提示 + 预处理建议（动态）
  └─ 今天日期

prompts_v2.py:build_messages()        → 历史消息 + 当前用户消息
```

**模型选择**：紧急 → `settings.emergency_model` (Kimi K2.5)，日常 → `settings.model` (Grok)

#### Phase 3: Orchestrator（核心 Agent Loop）
```
创建 asyncio.Queue 作为桥接
asyncio.create_task(_run_orchestrator_to_queue())   ← 后台 Task 运行 orchestrator
asyncio.create_task(_run_profile_extractor_llm())   ← 并行提取宠物档案信息
主循环消费 queue，yield SSE 事件给前端
```

### 6. `orchestrator.py:462` — `run_orchestrator()` 核心循环

```
for round in range(MAX_ROUNDS=5):
    │
    ├─ micro_compact(messages)              ← 压缩旧 tool_result 节省 token
    │
    ├─ _stream_completion()                 ← 流式调 LLM (litellm.acompletion)
    │   ├─ 每个 token → on_token() → queue → SSE "event: token" → 前端逐字显示
    │   └─ 收集 tool_calls（流式拼接 function name + arguments）
    │
    ├─ 如果没有 tool_calls:
    │   ├─ 检查 plan nag（plan 还有未完成步骤？→ 注入催促消息，continue）
    │   ├─ 检查 nudge（高置信度 ≥0.8 工具没调？→ 注入催促消息，continue）
    │   └─ 都不需要 → break 退出循环
    │
    └─ 如果有 tool_calls:
        ├─ 构建 assistant 消息（含 tool_calls）追加到 messages
        └─ 逐个调 dispatch_tool()
            └─ tool_result 序列化后作为 tool role 消息喂回，进入下一轮
```

### 7. `orchestrator.py:110` — `dispatch_tool()` 统一工具分发

```
解析 tool_call JSON
│
├─ 特殊拦截（确定性逻辑，不依赖 LLM）：
│   ├─ create_calendar_event 的宠物名校验（防 LLM 给错宠物创建事件）
│   ├─ create_calendar_event 自动补全 cost（正则从用户文本提取金额）
│   ├─ create_daily_task 自动补全 end_date（正则提取日期表达）
│   ├─ plan → 不走 DB，记录步骤列表，返回
│   └─ request_images → 返回 _inject_images 标记，主循环注入图片到消息
│
├─ Confirm 门控：fn_name in CONFIRM_TOOLS（delete_pet, delete_calendar_event 等）
│   → pending_actions.py:store_action() 预存工具名+参数到 DB（1小时 TTL）
│   → on_card() 推送 confirm_action 卡片给前端
│   → 返回 {"status": "waiting_confirm"}（不执行，等用户确认）
│
├─ validation.py:validate_tool_args() → 校验参数（UUID、日期、枚举、必填字段）
│   → 失败返回 {"error": "..."} → LLM 下一轮看到错误，自动修正参数重试
│
└─ tools/registry.py:execute_tool() → 查装饰器注册表，执行对应函数
    → 返回 {"success": true, "card": {...}}
    → card 通过 on_card() → queue → SSE "event: card" 推送给前端
```

#### Phase 4: 后处理（不阻塞 SSE 响应）
```
post_processor.py:execute_suggested_actions()
  └─ 最终兜底：orchestrator 里 nudge 也失败后，置信度 ≥0.8 的直接确定性执行

profile_extractor.py:merge_into_profile_md()
  └─ 并行 LLM 调用的结果回来了，将提取的宠物信息（品种、体重等）合并到档案

_save_message(assistant)
  └─ 保存完整回复 + 所有卡片 JSON 到 DB

context_agent.py:trigger_summary_if_needed()
  └─ 后台 Task：未摘要消息 ≥5 条时，用 LLM 压缩为结构化摘要存到 session

yield "event: __debug__"    ← 仅 X-Debug: true 时发送完整 trace
yield "event: done"         ← iOS 收到后停止 loading 动画
```

---

## 回到 iOS 端

### `ChatService.swift` 收到 SSE 事件
| SSE 事件 | iOS 处理 |
|----------|---------|
| `event: token` | `ChatStore` 逐字追加到 AI 消息气泡 |
| `event: card` | 解码成 `CardData`，插入卡片 UI（记录卡片、地图卡片等）|
| `event: emergency` | 显示红色紧急横幅 + 急救指导 |
| `event: done` | 停止 loading，保存 session_id 到 UserDefaults |

---

## 一条消息经过的文件清单

| 序号 | 文件 | 关键函数 | 作用 |
|------|------|---------|------|
| 1 | `ios-app/.../ChatView.swift` | 用户交互 | 发送按钮 |
| 2 | `ios-app/.../ChatStore.swift` | `sendMessage()` | 消息状态管理 |
| 3 | `ios-app/.../ChatService.swift` | `streamChat()` | 构建请求、SSE 解析 |
| 4 | `ios-app/.../APIClient.swift` | `streamRequest()` | JWT token + SSE 连接 |
| 5 | `backend/.../routers/chat.py` | `chat()` → `_event_generator()` | 入口 + 4 阶段主函数 |
| 6 | `backend/.../agents/locale.py` | `detect_language()` | 中/英文检测 |
| 7 | `backend/.../agents/emergency.py` | `detect_emergency()` | 紧急关键词匹配 |
| 8 | `backend/.../agents/pre_processing/` | `pre_process()` | 预分析 SuggestedAction |
| 9 | `backend/.../agents/prompts_v2.py` | `build_system_prompt()` | 组装 system prompt |
| 10 | `backend/.../agents/orchestrator.py` | `run_orchestrator()` | 核心 Agent Loop |
| 11 | `backend/.../agents/orchestrator.py` | `dispatch_tool()` | 统一工具分发 |
| 12 | `backend/.../agents/validation.py` | `validate_tool_args()` | 参数校验 → 自修复 |
| 13 | `backend/.../agents/tools/registry.py` | `execute_tool()` | 装饰器注册表执行 |
| 14 | `backend/.../agents/context_agent.py` | `trigger_summary_if_needed()` | 上下文压缩 |
| 15 | `backend/.../agents/profile_extractor.py` | `extract_profile_info()` | 并行档案提取 |

---

## 关键设计亮点（面试重点）

### 1. Orchestrator 单循环设计
一个 while 循环处理所有场景（纯聊天、单工具、多工具、图片、Plan 多步骤），取代了旧的 4 路径架构。通过 nudge 和 plan nag 机制应对 LLM 的不确定性。

### 2. 三层容错机制
- **预处理器** (`pre_process`): 提前检测用户意图，给出带置信度的 SuggestedAction
- **Nudge** (orchestrator 内): LLM 没调预期工具时，注入催促消息让它重试
- **兜底执行** (post_processor): Nudge 也失败后，高置信度动作直接确定性执行

### 3. 验证 → LLM 自修复循环
`validate_tool_args()` 返回错误列表（不抛异常），错误作为 tool result 喂回 LLM，LLM 在下一轮自动修正参数重试。

### 4. Confirm 门控的幂等设计
破坏性操作（删除宠物/事件）预存参数到 DB，用户确认后直接执行预存参数，不再问 LLM，防止"LLM 改口"。

### 5. 异步队列桥接
`asyncio.Queue` 解耦 orchestrator（慢，涉及 LLM 调用）和 SSE generator（快，需要即时响应）。Profile extractor 作为独立 Task 与主 orchestrator 并行运行。

### 6. 前缀缓存友好的 Prompt 顺序
System prompt 按 静态→半静态→动态 排列，最大化 LLM 前缀缓存命中率。

### 7. Debug Trace 零开销设计
`TraceCollector` 哨兵对象，`active=False` 时所有 `record()` 直接 return，零运行时开销。激活时并行发起非流式 LLM 调用捕获完整 JSON。
