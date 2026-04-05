# CozyPup

[English](README.md) | **中文**

AI 驱动的宠物健康助手。一个聊天界面搞定一切 — 记录事件、管理宠物档案、查找附近兽医、设置提醒。没有表单，没有按钮，没有引导流程。用户跟 AI 说话，AI 直接执行。

原生 SwiftUI iOS 应用 + FastAPI Python 后端 + PostgreSQL (Neon) + LLM (LiteLLM)。

**已部署在 Google Cloud Run。** iOS 应用在 TestFlight 内测中。

## 截图

<p align="center">
  <img src="Photos/IMG_1022.PNG" width="200" alt="首页 — 语音输入">
  <img src="Photos/IMG_1025.PNG" width="200" alt="聊天 — 事件记录 + 地点搜索">
  <img src="Photos/IMG_1026.PNG" width="200" alt="地点详情卡片 + 评论">
  <img src="Photos/IMG_1027.PNG" width="200" alt="日历时间线">
</p>

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│  iOS (SwiftUI)                                                  │
│  ChatView → ChatStore → ChatService (SSE) → APIClient          │
│  CalendarDrawer / Settings / Cards (PlaceCard, RecordCard, ...) │
└──────────────────────────┬──────────────────────────────────────┘
                           │ SSE (token / card / emergency / done)
┌──────────────────────────▼──────────────────────────────────────┐
│  FastAPI 后端                                                    │
│                                                                 │
│  POST /api/v1/chat ─── SSE EventSourceResponse                 │
│    │                                                            │
│    ├─ 阶段 0: 会话 + 消息持久化                                    │
│    ├─ 阶段 1: 并行预处理 (正则, <1ms)                               │
│    │   ├─ 紧急关键词检测                                           │
│    │   ├─ 意图提取 → SuggestedActions                             │
│    │   └─ 语言检测                                                │
│    ├─ 阶段 2: Prompt 组装 (缓存优化顺序)                            │
│    │   ├─ 工具定义 + 决策树 (100% 缓存命中)                         │
│    │   ├─ 宠物档案 (高缓存命中率)                                   │
│    │   ├─ 上下文摘要 (惰性压缩)                                    │
│    │   └─ 紧急/预处理器提示 (动态)                                  │
│    └─ 阶段 3: 编排器循环 (最多 5 轮)                                │
│        ├─ 流式 LLM → token 推送到客户端                            │
│        ├─ 工具调用 → 验证 → 执行 → 反馈                            │
│        ├─ Nudge: LLM 遗漏工具时重试                                │
│        └─ Plan nag: 强制多步骤完成                                 │
│                                                                 │
│  并行: 档案提取器 (异步, 非阻塞)                                    │
│  并行: 上下文压缩 (惰性, 基于阈值)                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 受约束 Agent 框架

核心理念：**LLM 的输出是建议，不是命令。** 每个工具调用都会经过验证、门控检查和自动纠错后才执行。确定性预处理器提供兜底 — 即使 LLM 失败，系统仍然会执行最可能的操作。

这使得我们可以使用更便宜、更快的模型（Grok 4.1 Fast 用于日常聊天，Kimi K2.5 用于紧急情况），同时保持通常需要昂贵模型才能达到的准确性。

### 六层架构

```
用户消息
    │
    ▼
┌─────────────────────────────────────────────────┐
│ 1. 预处理器 (确定性, <1ms)                        │
│    正则提取意图 + 参数 → SuggestedAction           │
│    每个操作的置信度 0.0-1.0                        │
│    作为提示注入系统 prompt                         │
└────────────────────┬────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────┐
│ 2. LLM 编排器 (流式, 最多 5 轮)                    │
│    LLM 通过函数调用决定操作                        │
│    每个工具调用经过第 3-5 层:                       │
│    ┌───────────────────────────────────────────┐ │
│    │ 3. 验证层 — 格式 + 类型检查                 │ │
│    │    错误反馈给 LLM 自动修正                   │ │
│    ├───────────────────────────────────────────┤ │
│    │ 4. 确认门控 — 拦截破坏性操作                 │ │
│    │    显示确认卡片, 延迟执行                    │ │
│    ├───────────────────────────────────────────┤ │
│    │ 5. 执行器 — 所有权检查 + 数据库写入          │ │
│    │    返回结果 + 前端卡片                      │ │
│    └───────────────────────────────────────────┘ │
│    LLM 遗漏工具 → NUDGE (重试一次)                │
│    计划未完成 → PLAN NAG (继续执行)               │
└────────────────────┬────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────┐
│ 6. 后处理器 (确定性兜底)                           │
│    如果 LLM 声称"已完成"但没调工具:                 │
│    直接执行预处理器的高置信度建议 (≥0.8)            │
└─────────────────────────────────────────────────┘
```

### 为什么这很重要

| 问题 | 朴素 LLM+Tools | 受约束 Agent |
|------|----------------|-------------|
| LLM 说"已记录"但没调工具 | 数据丢失 | 后处理器捕获并执行 |
| LLM 传了错误的日期格式 | 工具崩溃 | 验证器拒绝，LLM 自动修正 |
| LLM 把"遛狗+洗澡"合并成一条记录 | 数据丢失 | Plan 工具强制分解 |
| LLM 忘了调 search_places | "我不知道附近的兽医" | Nudge 机制重试并明确指令 |
| 用户说"删除我的宠物" | 立即删除 | 确认门控显示卡片，用户必须确认 |
| 紧急情况: "我的狗在抽搐" | 泛泛建议 | 关键词检测 → 模型升级 → trigger_emergency 工具 |

### 工具清单 (34 个工具)

| 领域 | 工具 |
|------|------|
| 日历 | create/query/update/delete_calendar_event, upload/remove_event_photo, add_event_location |
| 宠物 | create/delete_pet, update_pet_profile, set_pet_avatar, summarize_pet_profile, list_pets |
| 提醒 | create/update/delete/delete_all/list_reminders |
| 地点 | search_places, search_places_text, get_place_details, get_directions |
| 任务 | manage_daily_task |
| 其他 | draft_email, trigger_emergency, set_language, plan, request_images |

### 编排器循环细节

```python
# 简化的编排器流程 (orchestrator.py)

MAX_ROUNDS = 5

for round in range(MAX_ROUNDS):
    # 1. 流式 LLM 响应
    text, tool_calls = await stream_completion(messages, tools)

    if not tool_calls:
        # 2a. 检查计划完成度
        if plan_steps and not all_covered:
            inject_plan_nag()  # "你计划了3步但只做了2步"
            continue

        # 2b. 检查 nudge
        missed = find_missed_tools(suggested_actions, tools_called)
        if missed and not nudge_used:
            inject_nudge(missed)  # "你应该调用 search_places"
            continue

        break  # 正常退出

    # 3. 执行每个工具调用
    for tc in tool_calls:
        args = parse_arguments(tc)
        errors = validate_tool_args(tc.name, args)  # 第 3 层
        if errors:
            feed_error_to_llm(errors)
            continue

        if tc.name in CONFIRM_TOOLS:                # 第 4 层
            emit_confirm_card(tc)
            continue

        result = await execute_tool(tc.name, args)  # 第 5 层
        if result.get("card"):
            emit_card(result["card"])
        feed_result_to_llm(result)
```

---

## 上下文管理

### 惰性压缩 (`context_agent.py`)

CozyPup 不会把 20 条原始消息塞进 prompt，而是使用上下文 agent：

```
长期上下文: pet.profile_md (由 profile_extractor 自动更新)
短期上下文: session_summary (由 context_agent 压缩)
近期消息: 最近 3-5 条原始消息
```

**触发条件**: 当未摘要的消息 ≥ 5 条时，异步上下文 agent（廉价模型，temperature=0.1）将其压缩为结构化摘要：

```json
{
  "topics": ["讨论了疫苗计划", "记录了每日散步"],
  "key_facts": ["下次疫苗 4月15日到期", "兽医预约已确认"],
  "pending": "用户问了附近的美容店但还没选",
  "mood": "casual"
}
```

实现约 60-70% 的 token 压缩，同时保持对话连续性。

### 档案提取 (`profile_extractor.py`)

与主编排器并行运行（非阻塞）。从自然对话中提取宠物健康信息，合并到 `pet.profile_md`：

```
用户: "维尼对鸡肉过敏，上次吃了就吐"
→ 提取器检测: 宠物"维尼"的过敏信息
→ 合并到 profile_md 的 ## 健康 章节
→ 后续对话自动引用此信息
```

---

## 紧急流水线

```
用户消息: "我的狗在抽搐！"
    │
    ├─ emergency.py: 正则匹配"抽搐" → EmergencyCheckResult(detected=True)
    │
    ├─ 模型切换: 日常模型 (Grok 4.1 Fast) → 紧急模型 (Kimi K2.5)
    │
    ├─ Prompt 注入: "⚠️ 检测到紧急关键词: [抽搐]。评估情况，
    │   如果是真正的紧急情况则调用 trigger_emergency。"
    │
    └─ LLM 判断:
        ├─ 真正紧急 → trigger_emergency(action="find_er") → emergency SSE 事件
        └─ 误报 ("上次抽搐是什么时候") → 正常文字回复
```

关键：正则做廉价预过滤，LLM 做最终判断。避免纯关键词检测的误报。

---

## SSE 流式协议

```
event: token\ndata: {"text": "帮你"}\n\n
event: token\ndata: {"text": "记录了"}\n\n
event: card\ndata: {"type": "record", "pet_name": "维尼", "date": "2026-04-05", ...}\n\n
event: emergency\ndata: {"message": "...", "action": "find_er"}\n\n
event: done\ndata: {"intent": "chat", "session_id": "..."}\n\n
```

iOS `ChatService.swift` 将 SSE 事件解析为类型化的 `AsyncStream<SSEEvent>` 枚举，token 用于实时显示，card 用于结构化 UI 渲染。

---

## iOS 架构

```
ios-app/CozyPup/
├── Services/
│   ├── APIClient.swift       # Swift actor, JWT 管理, SSE 流式传输
│   ├── ChatService.swift     # SSE 解析器 → AsyncStream<SSEEvent>
│   ├── CalendarSyncService.swift  # EventKit 同步 (每个宠物独立日历)
│   └── SpeechService.swift   # 语音转文字
├── Stores/                   # @MainActor ObservableObject, API 优先
│   ├── ChatStore.swift       # 消息持久化, 每日会话重置
│   ├── CalendarStore.swift   # 通过 API 增删改查, Apple Calendar 同步
│   ├── PetStore.swift        # 宠物增删改查 + UserDefaults 缓存
│   └── AuthStore.swift       # Apple/Google OAuth + JWT
├── Models/
│   └── ChatMessage.swift     # CardData 枚举 (12 种卡片类型, 从 SSE 自动解码)
└── Views/
    ├── Chat/ChatView.swift   # 主聊天界面
    ├── Calendar/             # 时间线、消费统计、抽屉
    ├── Cards/                # PlaceCard, PlaceDetailCard, DirectionsCard, RecordCard, ...
    └── Settings/             # 宠物管理、日历同步、语言设置
```

**设计系统**: 灵感来自 Timepage 的极简美学。所有 UI 使用 `Tokens.*`（颜色、字体、间距、圆角）— 零硬编码值。

---

## 后端结构

```
backend/app/
├── main.py                   # 应用工厂, 中间件栈
├── config.py                 # pydantic-settings 从环境变量读取
├── auth.py                   # JWT + Apple/Google OAuth
├── models.py                 # SQLAlchemy 模型 (User, Pet, CalendarEvent, Reminder, ...)
├── database.py               # 异步引擎 + 会话
├── routers/                  # REST 端点 (chat, calendar, pets, reminders, ...)
├── agents/
│   ├── orchestrator.py       # 统一循环: 流式 → 分发 → 验证 → 执行
│   ├── validation.py         # 每个工具的参数验证器 + 自动纠错
│   ├── locale.py             # 双语 prompt + 工具决策树
│   ├── prompts_v2.py         # 缓存优化的 prompt 组装
│   ├── emergency.py          # 关键词检测 + 模型路由
│   ├── context_agent.py      # 惰性上下文压缩
│   ├── profile_extractor.py  # 并行宠物档案enrichment
│   ├── post_processor.py     # 确定性兜底执行
│   ├── trace_collector.py    # 调试跟踪 (X-Debug: true 头)
│   ├── constants.py          # CONFIRM_TOOLS, MAX_ROUNDS
│   ├── pre_processing/       # 基于正则的意图提取 (6 个领域模块)
│   └── tools/
│       ├── definitions.py    # 34 个工具定义 (LLM function calling)
│       ├── registry.py       # @register_tool 装饰器
│       ├── calendar.py       # 事件增删改查 + 照片 + 位置
│       ├── pets.py           # 宠物管理 + 档案
│       ├── reminders.py      # 推送通知提醒
│       ├── misc.py           # 地点、邮件、紧急、语言、导航
│       └── tasks.py          # 每日任务管理
├── services/
│   ├── places.py             # Google Places + Directions API (带缓存)
│   └── push.py               # APNs 推送通知
├── middleware/                # 限流, CORS
└── debug/                    # 结构化日志, 错误快照, CLI 工具
```

---

## 部署

- **后端**: Google Cloud Run (蒙特利尔), 推送到 main 分支自动部署 (Cloud Build)
- **数据库**: Neon PostgreSQL (Serverless)
- **LLM**: LiteLLM → Grok 4.1 Fast (日常) / Kimi K2.5 (紧急)
- **存储**: GCS 存储桶存放宠物头像 + 本地磁盘存放事件照片
- **密钥**: Google Secret Manager

---

## 技术栈

| 层级 | 技术 |
|------|------|
| iOS | SwiftUI, Combine, MapKit, EventKit, Speech |
| 后端 | FastAPI, SQLAlchemy (async), Alembic, LiteLLM |
| 数据库 | PostgreSQL (Neon serverless) |
| LLM | Grok 4.1 Fast, Kimi K2.5 (via LiteLLM) |
| 地图 | Google Places API, Google Directions API |
| 认证 | Apple Sign-In, Google Sign-In, JWT |
| 部署 | Google Cloud Run, Cloud Build, Secret Manager |
| 推送 | APNs (Apple Push Notification service) |

---

## 核心设计决策

1. **纯聊天输入** — 没有表单，没有引导。一切通过自然对话完成。
2. **编排器 + 执行器** — LLM 决定*做什么*（函数调用），纯代码*执行*（数据库写入、API 调用）。
3. **受约束 Agent** — 验证 + nudge + 计划跟踪 + 后处理器，让廉价模型也能可靠工作。
4. **每日会话** — 每个日历日一个聊天会话，首条消息时自动创建。
5. **双模型路由** — 快速模型用于聊天，精确模型用于紧急情况。
6. **API 优先 iOS** — Store 先调后端，失败时回退到 UserDefaults 缓存。
7. **SSE 流式传输** — 实时 token 显示 + 结构化卡片，在单一流中传递。

---

## 开发

### 后端
```bash
cd backend
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

### iOS
在 Xcode 中打开 `ios-app/CozyPup.xcodeproj` → Cmd+R。需要 Xcode 16+，部署目标 iOS 17.0。

### 测试
```bash
cd backend && pytest tests/ -v
```
