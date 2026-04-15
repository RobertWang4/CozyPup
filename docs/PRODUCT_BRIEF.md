# CozyPup 产品报告

> 基于真实代码与数据库模型整理。这份文档记录产品的全部功能、数据、交互与技术决策。供下游 agent 生成推广素材、App Store 描述、帮助文档、PR 稿等使用。
>
> 最后更新：2026-04-12

---

## 一、产品定位

CozyPup 是一款 AI 驱动的宠物健康助手，原生 iOS App（SwiftUI），后端 FastAPI + PostgreSQL，部署在 Google Cloud Run。

产品的核心交互是**自然语言对话**。用户不填表、不点按钮，全部操作通过跟 AI 说话完成：记录宠物日常、设置提醒、查找附近医院、询问健康问题、管理多宠物档案，都在一个聊天界面里。

支持中文和英文，自动检测系统语言，也可在对话中切换。

---

## 二、当前状态

- **后端**：已上线，部署在 Google Cloud Run（蒙特利尔），推送 main 分支自动部署
- **iOS App**：TestFlight 内测阶段，bundle ID `com.cozypup.app`，最低 iOS 17
- **数据库**：Neon PostgreSQL（serverless），包含 pgvector 扩展用于知识库检索
- **认证**：Apple Sign In、Google Sign In（生产）、dev email 登录（测试用）
- **订阅**：App Store 内购（StoreKit 2），试用期 7 天后需订阅

---

## 三、用户可用功能一览

下面按用户能直接感知到的功能模块组织。

### 1. 聊天（主界面）

用户打开 App 看到的主界面就是 ChatView。所有核心操作都从这里发起。

**输入方式**：
- 文字输入
- 语音输入：长按麦克风录音，显示波形，上滑取消；录音结束后自动转文字；实时显示检测到的语言
- 图片输入：点 `+` 按钮从相册选或相机拍，最多 9 张；支持拍后裁剪
- 快捷 chips：输入框上方有 6 个预设按钮（添加宠物 / 健康咨询 / 设个提醒 / 附近医院 / 今日待办 / 喂养记录），点击直接发送对应消息
- 斜杠命令：`/clear` 清空当前会话、`/savechat` 保存当前会话、`/loadchat` 加载已保存的会话

**输出方式**：
- AI 回复以流式 token 展示（边想边打）
- 富卡片 UI：根据 AI 调用的工具，聊天流里会穿插结构化卡片（见下方「卡片类型」）
- 紧急响应：触发急诊工具时会显示红色横幅 + 触觉反馈 + 一键操作按钮

**会话机制**：
- 每个自然日一个聊天会话（session），首条消息时自动创建
- 历史会话可以保存并命名，随时重新加载继续对话
- 过期的临时会话会自动清理

### 2. 宠物档案

每个用户可以管理多只宠物。字段包括：
- 基础：名字、物种（狗/猫/其他，一旦设定不可改）、品种、生日、体重、性别、是否绝育、毛色
- 视觉：头像（用户上传或从聊天图片中指定）
- 展示色：每只宠物有独立的色标色（`color_hex`）用于 UI 区分
- **Profile JSON**：灵活的键值对存储任意信息（过敏、饮食、兽医、性格等）
- **Profile Markdown**：narrative 格式的宠物档案，AI 在对话中自动学习并写入，约 500-800 字

**自动学习机制**：Profile Extractor 在后台异步运行，从每次对话中提取宠物健康信息合并到 `profile_md`。例如用户说"维尼对鸡肉过敏，上次吃了就吐"，下次 AI 回答时会自动知道维尼过敏鸡肉。

**操作方式**：
- 通过对话创建、修改、删除（AI 调用对应工具）
- 也可在 Settings Drawer → 宠物列表 → PetFormView 手动编辑
- PetProfileEditor 查看/编辑完整的 profile_md

### 3. 日历与事件记录

所有"已发生/即将发生的事"都记录为 CalendarEvent。

**字段**：
- 日期（必填）、时间（可选，HH:MM）
- 标题、类型（log/appointment/reminder）、分类（daily/diet/medical/abnormal 等）
- 原始文本（用户原话）、是否被编辑过、来源（chat/manual）
- 照片（列表）
- 地点（名字、地址、经纬度、Google place_id）
- 花费（cost，浮点数）
- 提醒时间（`reminder_at`，配合推送通知）
- **pet_ids 数组**：支持一个事件关联多只宠物
- **created_by**：记录事件是由哪个用户录入的（用于共享宠物场景）

**展示界面**：
- `CalendarDrawer`：从聊天界面左侧滑出，展示月历
- `MonthGrid`：月视图，每天显示该日事件数量
- `HeatStripView`：顶部色带，每天用颜色深浅表示活跃度（事件多少）
- `SingleDayTimelineView`：单日时间线视图
- `MultiDayTimelineView`：多日连续视图（周视图等）
- `TimelineEventCard`：单条事件卡片（标题、分类图标、时间、花费、照片、地点）
- `EventEditSheet`：点击事件进入编辑界面
- `LocationPickerSheet`：地图选点
- `DayChatSheet` / `ReadOnlyChatView`：某天对应的聊天记录回看

**花费统计**：
- `SpendingStatsView`：按分类统计花费（饼图/柱状图）
- 所有带 `cost` 字段的事件都会被统计

### 4. 每日待办任务

与一次性事件（CalendarEvent）区分开的一种"重复性任务"模型。

**类型**：
- `routine`：永久每日任务（如每天遛狗）
- `special`：有截止日期的任务（如未来 7 天每天喂益生菌），需要传 `end_date`

**字段**：标题、每日目标次数（daily_target，默认 1）、start_date、end_date（可选）、关联宠物（可选）、是否激活

**完成追踪**：
- `DailyTaskCompletion` 表按 `(task_id, date)` 记录完成次数
- UI 显示当日已完成次数 / 目标次数
- 可点击「+」增加、「-」减少

**界面**：
- `DailyTaskManagerSheet`：管理所有每日待办
- `DailyTaskCard`：聊天流中 AI 创建/显示待办的卡片
- iOS 聊天顶部可打开今日待办浮层

**端点**：
- `GET /tasks/today` – 当天所有活跃任务 + 完成情况
- `POST /tasks/{task_id}/tap` / `untap` – 完成次数增减

### 5. 提醒（Reminder）与推送

CozyPup 有两种"提醒"概念：
1. **CalendarEvent + reminder_at**：推荐方式。在创建事件时指定提醒时间，后台到点推送
2. **独立 Reminder 表**（Legacy）：存储标题、body、trigger_at、type（medication/vaccine/checkup/feeding/grooming/other）

**推送通知**：
- APNs（Apple Push Notification service）
- 设备注册：`POST /devices` 存 device token
- 配置项：`APNS_KEY_PATH` / `APNS_KEY_ID` / `APNS_TEAM_ID` / `APNS_BUNDLE_ID` / `APNS_USE_SANDBOX`

**用户控制**：AI 可以调 `list_reminders` / `update_reminder` / `delete_reminder` / `delete_all_reminders`。删除类操作都需要用户确认。

### 6. 附近医院 / 地点查找

接入 Google Places API 和 Directions API。

**工具**：
- `search_places`：按关键词（如"24 小时宠物急诊"）和半径搜索
- `search_places_text`：按文本精确搜索特定地址/名字
- `get_place_details`：拉取某个地点的详情（营业时间、评论、电话、服务）
- `get_directions`：生成导航信息（驾车/步行，距离、时长）
- `add_event_location`：把地点绑定到某个 CalendarEvent

**卡片**：
- `PlaceCard`：单个地点（名字、评分、地址、距离、一键拨号、导航）
- `PlaceDetailCard`：详情（营业时间、评论、照片、电话、网站）
- `DirectionsCard`：导航路线（距离、时长、预览、一键打开系统地图）
- `LocationPickerCard`：地图选点（用于手动指定事件地点）

### 7. 健康知识库（RAG）

面向宠物健康问答场景的检索增强生成。

**数据**：
- `KnowledgeArticle` 表存外部知识文章（标题、内容、分类、物种、URL、元数据）
- 使用 OpenAI text-embedding-3-small（1536 维）生成向量
- 向量存储在 `Embedding` 表（pgvector），`source_type` 标识来源（knowledge_base / chat_turn / daily_summary / calendar_event）

**检索流程**（`search_knowledge` 工具）：
1. 用户问健康问题 → LLM 调用 `search_knowledge`
2. 后端同时查两个源：全局知识库 + 用户自己的历史记录
3. 按物种过滤（dog/cat/all）
4. 返回 Top-K = 3 个最相关结果（`{knowledge: [...], history: [...]}`
5. LLM 基于结果 + 宠物档案生成个性化回答

**iOS 展示**：
- `ReferencesCard`：消息下方的"References"按钮，点击弹出 drawer，展示引用来源（标题、片段、可点击 URL）

**知识库管理**（CLI）：
```bash
python -m app.rag.ingest --file knowledge/dog_vomiting.md --species dog --category 消化系统
python -m app.rag.ingest --dir knowledge/ --species dog
python -m app.rag.ingest --stats
```
格式：Markdown，可选 YAML frontmatter（title、url）；按段落切分为 ~400 字 chunk。

**现状**：RAG pipeline 已搭好，待填充大量知识库内容。

### 8. 紧急响应

**关键词识别**：后端 `emergency.py` 维护一组紧急关键词（36 个中英文），正则匹配用户消息，命中后：
- 抽搐 / 中毒 / 窒息 / 出血 / 呼吸困难 / 昏倒 / 失去意识 / 被车撞 / 误食毒物 / 痉挛 / 瘫痪 / 胃扭转 / 中暑 / 溺水 / 触电 / 蛇咬 / 过敏反应 / 快死了 / 等等

**模型路由**：
- 日常对话模型：`grok-4-1-fast`（快、便宜）
- 紧急模型：`kimi-k2.5`（更准确，安全导向）
- 一旦检测到紧急关键词，自动切换到紧急模型

**Prompt 注入**：检测到关键词时向系统 prompt 注入急诊提示，要求 LLM 判断是否真的紧急，如果是则调用 `trigger_emergency` 工具。

**iOS 响应**：
- `EmergencyBanner`：红色横幅组件，标题 + 说明 + 操作按钮
- 触发触觉反馈
- `trigger_emergency` 工具有 action 参数：`find_er`（找急诊）/ `call_vet`（联系兽医）/ `first_aid`（急救指引）

**误报处理**：LLM 会判断是否真的是紧急情况。如"上次中毒是什么时候"不会触发急诊，"狗狗现在中毒了"会触发。

### 9. 宠物共享（核心卖点之一）

两个人共同照顾同一只宠物。

**触发条件**：需要 Duo 订阅（`com.cozypup.app.{weekly,monthly,yearly}.duo`）

**机制**：
- 使用者 A（已订阅 Duo）在 Settings → Family Settings 邀请 B
- 两种邀请方式：
  1. **邮箱邀请**：`POST /family/invite` 发送邀请，B 收到后点击接受
  2. **二维码邀请**：A 生成宠物级别的 share token（`POST /pets/{pet_id}/share-token`），token 10 分钟过期；B 用 QRScannerView 扫码，`POST /pets/accept-share` 接受

**共享范围**：
- 宠物档案（名字、品种、健康信息、profile_md 等）
- 所有 CalendarEvent
- 所有 Reminder
- 所有 DailyTask 和 completion 进度
- 聊天历史各自独立，但 AI 能看到对方的操作历史（通过 `created_by` 字段）

**数据模型**：
- `PetCoOwner`（pet_id, user_id）唯一约束：多对多
- `PetShareToken`（token、10 分钟 TTL、used 标志）
- `FamilyInvite`（邀请方、被邀请邮箱、状态）
- `User.family_role`（payer / member）
- `User.family_payer_id`

**商业规则**：
- 只有支付 Duo 订阅的 payer 才能邀请
- 每个 payer 最多一个 member
- payer 降级到 Individual 订阅时，member 会被自动踢出（revoke）
- member 接受邀请后立即获得 active 订阅状态

**退出机制**：
- `POST /pets/{pet_id}/unshare`：co-owner 离开共享宠物
- 可选：**保留深拷贝**（创建一只新 pet，复制所有事件/提醒到自己名下）

**iOS 界面**：
- `FamilySettingsView`：管理伴侣（查看、撤销、pending 邀请）
- `PetShareSheet`：生成 QR / 管理 co-owner
- `PetUnshareSheet`：离开共享，选择是否保留副本
- `PetMergeSheet`：接受共享时可选合并到自己已有的宠物

### 10. 订阅体系

**产品 ID**（StoreKit）：
- 个人版：`com.cozypup.app.weekly` / `.monthly` / `.yearly`
- Duo 版：`com.cozypup.app.weekly.duo` / `.monthly.duo` / `.yearly.duo`

**状态流转**：
- 新用户默认 `trial` 状态（7 天试用）
- 试用期内 `trial_days_left` 递减
- 通过 StoreKit 购买 → `POST /subscription/verify` 验证交易 → 状态切到 `active`
- 到期未续费 → `expired`

**价格**（仅为 iOS fallback，实际以 StoreKit 为准）：
- 个人版：$1.99 / 周、$6.99 / 月、$59.99 / 年
- Duo 版：$2.99 / 周、$9.99 / 月、$89.99 / 年
- 月卡标记 `MOST POPULAR`，Yearly 标注 `SAVE 29%`，Monthly 标注 `SAVE 19%`

**端点**：
- `GET /subscription/status`：返回 `{status, trial_days_left, expires_at, product_id, is_duo}`
- `GET /subscription/trial-stats`：返回试用期使用量 `{chat_count, event_count, reminder_count}`
- `POST /subscription/verify`：验证 StoreKit transaction 并激活
- `POST /subscription/webhook`：App Store Server Notifications V2 占位

**Paywall 表现**：
- `PaywallSheet`：可软（soft）可硬（hard）。soft 时可关闭，hard 时必须订阅或恢复购买才能继续使用
- 软 paywall 在试用即将结束时弹出
- 硬 paywall 在试用过期后强制展示
- 显示试用期使用数据（chat/event/reminder 条数）作为说服素材
- 当前订阅的 plan 右上角有"当前订阅"绿色 badge（仅在已订阅状态可见）
- 支持 `Restore Purchase`

**订阅门控**：`/chat` 端点有 `require_active_subscription` 中间件，过期后无法聊天。

### 11. 用户与账户

**User 字段**：
- id、email（唯一）、name、auth_provider（apple/google/email/dev）
- avatar_url（GCS 存储桶 `cozypup-avatars`）
- phone_number
- subscription_status / trial_start_date / subscription_expires_at / subscription_product_id
- family_role / family_payer_id

**端点**：
- `POST /auth/apple` / `POST /auth/google`：OAuth 登录
- `POST /auth/dev`：开发测试登录（无 OAuth，仅 email + name）
- `POST /auth/refresh`：用 refresh_token 换新的 access_token
- `GET /auth/me`：拉取当前用户资料
- `PATCH /auth/me`：改名字
- `DELETE /auth/me`：删除账号
- `POST /auth/me/avatar`：上传用户头像

**JWT**：access_token 60 分钟 TTL + refresh_token 30 天 TTL

### 12. 语言支持

两种语言：**中文 (zh)** 和 **英文 (en)**。

**切换逻辑**：
- 首次使用时自动检测（系统语言 / CJK 字符正则）
- 用户可通过 Settings 手动切换，或在对话中说"switch to English"/"切换成中文"，AI 调用 `set_language` 工具
- 所有 UI 字符串通过 `L.xxx` 计算属性管理（`Theme/L.swift`），后端通过 `locale.py` 的 `t()` 函数管理
- LLM system prompt 里明确要求按用户语言回复

### 13. Apple Calendar 同步

`CalendarSyncService.swift` 提供与系统日历的双向桥接。

**机制**：
- 每只宠物对应一个独立的 Apple Calendar（名字如"CozyPup - 维尼"）
- 通过 EventKit 读写
- `CalendarEvent` → `EKEvent` 映射

**同步范围**：
- `bulkSync()`：拉取当月事件批量同步
- `syncEvent()`：单个事件同步
- 单向同步（App → 系统日历）

**用户控制**：Settings 里开关 `CalendarSyncService.isSyncEnabled`。AI 也有 `sync_calendar` 工具引导用户开启。

### 14. 上下文压缩与档案提取

**上下文压缩**（`context_agent.py`）：
- 当会话中未压缩消息数 ≥ 阈值时，异步触发 Context Agent
- 用便宜的模型（`CONTEXT_MODEL`）把旧消息压缩成结构化 JSON 摘要
- 摘要格式：`{topics, key_facts, pending, mood}`
- 存入 `ChatSession.context_summary` (JSONB) + `summarized_up_to`
- 节省约 60-70% 的 prompt token

**档案提取**（`profile_extractor.py`）：
- 主对话循环的并行异步任务，不阻塞用户响应
- 从对话中提取宠物健康信息
- 合并到 `Pet.profile` (JSON) 和 `Pet.profile_md` (markdown)
- 下次对话时自动被加载进 system prompt，AI 记住这些事实

---

## 四、AI Agent 架构

### 工具总数

当前共 **38 个工具**，按领域分组：

| 领域 | 工具 |
|---|---|
| 日历事件 | `create_calendar_event`、`query_calendar_events`、`update_calendar_event`、`delete_calendar_event`、`upload_event_photo`、`remove_event_photo`、`add_event_location` |
| 宠物档案 | `create_pet`、`delete_pet`、`update_pet_profile`、`save_pet_profile_md`、`summarize_pet_profile`、`list_pets`、`set_pet_avatar` |
| 提醒 | `create_reminder`、`list_reminders`、`update_reminder`、`delete_reminder`、`delete_all_reminders` |
| 每日待办 | `create_daily_task`、`list_daily_tasks`、`manage_daily_task` |
| 地点 | `search_places`、`search_places_text`、`get_place_details`、`get_directions` |
| 紧急 | `trigger_emergency` |
| 知识库 | `search_knowledge` |
| 多步规划 | `plan` |
| 图像 | `request_images` |
| 语言 | `set_language` |
| 其他 | `draft_email`、`introduce_product`、`sync_calendar` |

### 受约束 Agent 框架（Constrained Agent）

核心理念：**LLM 的输出是建议而非命令**。每个工具调用经过六层验证与处理：

```
用户消息
    ↓
1. 预处理器（<1ms，纯正则）
   提取意图 + 参数 → SuggestedAction（带 0-1 置信度）
   作为 hint 注入 system prompt
    ↓
2. LLM Orchestrator（流式，最多 5 轮）
   LLM 通过 function calling 决定调用哪些工具
   ↓
   每个工具调用依次经过 3-5 层：
   ┌────────────────────────┐
   │ 3. 验证层               │
   │   类型、格式、必填字段   │
   │   错误反馈给 LLM 修正    │
   ├────────────────────────┤
   │ 4. 确认门控             │
   │   拦截破坏性操作        │
   │   显示 ConfirmActionCard│
   │   用户点击后才执行      │
   ├────────────────────────┤
   │ 5. 执行层               │
   │   所有权检查 + DB 写入  │
   │   返回 result + card    │
   └────────────────────────┘
   LLM 漏调工具 → Nudge（重试一次）
   Plan 未完成 → Plan Nag（继续）
    ↓
6. 后处理器（兜底）
   如果 LLM 说"已完成"但没调工具
   → 代码直接执行预处理器的高置信建议
```

### 双模型路由

- **日常模型**：`grok-4-1-fast`（便宜、快速，SSE 流式）
- **紧急模型**：`kimi-k2.5`（准确、安全）
- **上下文压缩模型**：廉价模型 + temperature=0.1
- **Embedding**：`text-embedding-3-small`
- 所有模型通过 LiteLLM 代理，统一接口

### 多步规划（Plan 工具）

当用户一句话包含多件事时，LLM 必须先调 `plan` 工具拆分：

```
用户：今天遛了狗还洗了澡
LLM → plan(steps=[
  {id: 1, action: "记录遛狗", tool: "create_calendar_event"},
  {id: 2, action: "记录洗澡", tool: "create_calendar_event"}
])
→ orchestrator 循环执行每一步
```

**Plan Nag**：如果 LLM 制定了 3 步的计划但只执行了 2 步，orchestrator 会强制 LLM 继续执行未完成的步骤。

### Nudge 机制

如果预处理器检测到用户有明显意图（例如"找附近医院"），但 LLM 没调用对应工具（`search_places`），orchestrator 会注入 nudge：

```
⚠️ 用户要找附近医院，你应该调用 search_places 工具，不要只回复文字。
```

### 破坏性操作确认

**CONFIRM_TOOLS**（无条件确认）：
- `delete_pet` / `delete_calendar_event` / `delete_reminder` / `delete_all_reminders`

**CONDITIONAL_CONFIRM_ACTIONS**（按参数条件确认）：
- `manage_daily_task` 的 action = `delete` / `delete_all` / `deactivate`

所有确认都走同一套流程：
1. 工具被拦截
2. 生成人类可读的描述（如"清空所有每日待办"）
3. `store_action` 存入 `PendingAction` 表，返回 action_id
4. 前端收到 `ConfirmActionCard`（带描述 + 确认/取消按钮）
5. 用户点确认 → `POST /chat/confirm-action { action_id }` → 后端从 PendingAction 取出 tool_name + arguments 执行
6. PendingAction 一小时内有效，过期失效

### Trace 与调试

开启 `X-Debug: true` header 时，服务端会收集整个 pipeline 的结构化 trace：
- chat_request（用户消息、session_id）
- llm_request / llm_response（每一轮的 prompt、tokens、工具调用）
- tool_call / tool_result
- chat_response（最终文本、卡片、工具列表、token 总数）
- 通过 SSE 的 `__debug__` 事件发送给前端

持久日志写到 `cozypup.trace` logger → Google Cloud Logging，每条带 `correlation_id` + `user_id`。

**Debug CLI**（`backend/app/debug/`）：
- `debug lookup <email>` — 查用户 ID
- `debug requests --user <id> --last 10` — 最近的请求
- `debug trace <correlation_id>` — 完整请求链
- `debug tokens --user <id> --period 7d` — token 用量
- `debug errors --module <m>` / `debug modules` / `debug replay <cid>` / `debug generate-test <cid>`

---

## 五、Backend API 端点汇总

所有业务端点都在 `/api/v1` 前缀下，除登录外均要求 JWT Bearer token。

### 认证 `/auth`
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/apple` | Apple Sign-In |
| POST | `/google` | Google Sign-In |
| POST | `/dev` | 开发登录（测试用） |
| POST | `/refresh` | 刷新 access_token |
| GET | `/me` | 拉取用户资料 |
| PATCH | `/me` | 修改名字 |
| DELETE | `/me` | 删除账号 |
| POST | `/me/avatar` | 上传用户头像 |

### 聊天 `/chat`
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/chat` | SSE 流式聊天（核心端点） |
| POST | `/chat/confirm-action` | 确认 pending action |
| GET | `/chat/history` | 会话消息历史 |
| GET | `/chat/sessions` | 所有 daily session 列表 |
| GET | `/chat/sessions/saved` | 已保存的会话 |
| POST | `/chat/sessions/{id}/save` | 保存会话并命名 |
| POST | `/chat/sessions/{id}/resume` | 恢复已保存的会话 |

### 宠物 `/pets`
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/` | 创建宠物 |
| GET | `/` | 列出所有宠物（含共享的） |
| GET | `/{pet_id}` | 单只宠物详情 |
| PUT | `/{pet_id}` | 修改宠物 |
| DELETE | `/{pet_id}` | 删除宠物 |
| POST | `/{pet_id}/avatar` | 上传头像 |
| GET | `/{pet_id}/avatar` | 拉取头像 |
| POST | `/{pet_id}/share-token` | 生成共享二维码 token |
| POST | `/accept-share` | 接受宠物共享 |
| POST | `/{pet_id}/unshare` | 离开共享宠物 |

### 日历 `/calendar`
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/` | 创建事件 |
| GET | `/` | 按日期范围、分类查询事件 |
| GET | `/{event_id}` | 单个事件详情 |
| PUT | `/{event_id}` | 修改事件 |
| DELETE | `/{event_id}` | 删除事件 |
| POST | `/{event_id}/photos` | 附加照片 |
| DELETE | `/{event_id}/photos` | 移除照片 |
| PUT | `/{event_id}/location` | 设置地点 |
| DELETE | `/{event_id}/location` | 清除地点 |
| GET | `/photos/{filename}` | 拉取事件照片 |

### 提醒 `/reminders`
| POST `/` | 创建提醒 |
| GET `/` | 列出所有待发提醒 |
| PUT `/{reminder_id}` | 修改 |
| DELETE `/{reminder_id}` | 删除 |

### 每日待办 `/tasks`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/today` | 今日所有活跃任务 + 完成情况 |
| POST | `/` | 创建任务 |
| PUT | `/{task_id}` | 修改任务 |
| DELETE | `/{task_id}` | 删除任务 |
| POST | `/{task_id}/tap` | 完成数 +1 |
| POST | `/{task_id}/untap` | 完成数 -1 |

### 地点 `/places`
| GET `/nearby` | 按半径搜索 |
| GET `/search` | 按文本搜索 |

### 订阅 `/subscription`
| GET `/status` | 订阅状态 + 试用天数 |
| GET `/trial-stats` | 试用期使用量 |
| POST `/verify` | 验证 StoreKit 交易 |
| POST `/webhook` | App Store 通知回调（占位） |

### 家庭（Duo）`/family`
| GET `/status` | 家庭关系状态 |
| POST `/invite` | 邀请伙伴 |
| POST `/accept` | 接受邀请 |
| POST `/revoke` | 撤销伙伴 |

### 设备 `/devices`
| POST `/` | 注册 APNs token |
| DELETE `/{token}` | 注销 |

### 中间件栈
从外到内：Correlation（生成 correlation_id）→ RequestLogging → ErrorCapture → ChatRateLimit（30 条/小时）→ CORS

---

## 六、SSE 聊天流格式

核心端点 `POST /chat` 返回 `text/event-stream`，事件类型如下：

```
event: token        # 流式 token（正常回复文本）
data: {"text": "帮你"}

event: card         # 结构化卡片（记录、地点、待办等）
data: {"type": "record", "title": "...", ...}

event: emergency    # 紧急卡片（红色横幅）
data: {"message": "...", "action": "find_er"}

event: __debug__    # 调试 trace（仅 X-Debug: true 时）
data: {...}

event: done         # 流结束
data: {"intent": "chat", "session_id": "..."}
```

iOS `ChatService.swift` 把 SSE 解析成 `AsyncStream<SSEEvent>` 枚举，token 用于实时打字效果，card 用于 UI 结构化渲染。

---

## 七、iOS 卡片类型（在聊天流中渲染）

| 卡片类型 | 触发工具 | 内容 |
|---|---|---|
| `RecordCard` | `create_calendar_event` / `update_calendar_event` | 事件标题、日期、宠物、分类图标、地点徽章、花费、照片 |
| `PlaceCard` | `search_places` | 地点名字、评分、地址、距离、拨号、导航按钮 |
| `PlaceDetailCard` | `get_place_details` | 营业时间、评论、照片、电话、网站 |
| `DirectionsCard` | `get_directions` | 距离、时长、路线预览、打开地图 |
| `ConfirmActionCard` | 任何需要确认的工具 | 动作描述、确认/取消 |
| `EmailCard` | `draft_email` | 草稿内容、主题、收件人、发送按钮 |
| `DailyTaskCard` | 待办相关工具 | 任务标题、目标、已完成次数、tap 按钮 |
| `ReferencesCard` | `search_knowledge` | 知识库来源列表（标题、片段、URL） |
| `LocationPickerCard` | `add_event_location` 过程中 | 地图选点 |
| `EmergencyBanner` | `trigger_emergency` | 红色横幅、一键找急诊/拨打/急救指引 |
| `ActionCard` | 通用 | 图标、标题、CTA 按钮 |
| `WhatsNewCard` | `introduce_product` | 功能介绍 |

---

## 八、数据模型全貌

PostgreSQL，所有表用 UUID 做主键。

| 模型 | 关键字段 | 说明 |
|---|---|---|
| `User` | email, auth_provider, subscription_status, trial_start_date, subscription_expires_at, subscription_product_id, family_role, family_payer_id | 用户 |
| `Pet` | user_id, name, species(locked), breed, birthday, weight, avatar_url, color_hex, profile(JSON), profile_md(markdown) | 宠物档案 |
| `PetCoOwner` | pet_id, user_id (unique) | 宠物共享 |
| `PetShareToken` | pet_id, owner_id, token, expires_at, used | 二维码分享 |
| `FamilyInvite` | inviter_id, invitee_email, invitee_id, status | 家庭邀请 |
| `ChatSession` | user_id, session_date, context_summary(JSONB), summarized_up_to, is_saved, title, expires_at | 每日会话 |
| `Chat` | session_id, user_id, role(user/assistant), content, cards_json, image_urls | 单条消息 |
| `CalendarEvent` | user_id, pet_id, pet_ids(JSON), event_date, event_time, title, category, cost, photos, location_*, reminder_at, created_by | 事件/记录 |
| `Reminder` | user_id, pet_id, type, title, body, trigger_at, sent, created_by | 旧的提醒模型 |
| `DailyTask` | user_id, pet_id, title, type(routine/special), daily_target, start_date, end_date, active | 每日待办 |
| `DailyTaskCompletion` | task_id, date, count (unique on task_id+date) | 完成进度 |
| `DeviceToken` | user_id, token, platform | APNs 注册 |
| `PendingAction` | user_id, session_id, tool_name, arguments(JSON), description | 待确认动作 |
| `KnowledgeArticle` | title, content, category, species, url, metadata_json | 外部知识文章 |
| `Embedding` | user_id, pet_id, source_type, source_id, content, embedding(pgvector 1536), metadata_json | 向量存储 |
| `DailySummary` | user_id, session_id, session_date, summary (unique per day) | 每日对话摘要 |

---

## 九、技术栈

| 层 | 技术 |
|---|---|
| iOS | Swift / SwiftUI / Combine / MapKit / EventKit / Speech / StoreKit 2 |
| 后端 | FastAPI、SQLAlchemy async、Alembic、Pydantic v2 |
| 数据库 | PostgreSQL (Neon serverless) + pgvector |
| LLM | LiteLLM 代理 → Grok 4.1 Fast（日常）、Kimi K2.5（紧急）、text-embedding-3-small |
| 地图 | Google Places API、Google Directions API |
| 认证 | Apple Sign-In、Google Sign-In、JWT |
| 推送 | APNs（Apple Push Notification service） |
| 部署 | Google Cloud Run（蒙特利尔）、Cloud Build、Google Secret Manager |
| 存储 | Google Cloud Storage（头像桶 `cozypup-avatars`）+ 本地磁盘（事件照片） |
| 监控 | Google Cloud Logging（结构化 JSON trace） |

---

## 十、iOS 应用结构

```
ios-app/CozyPup/
├── CozyPupApp.swift          // 入口：认证 → 免责声明 → Onboarding → ChatView
├── Services/
│   ├── APIClient.swift       // Swift actor, JWT 管理, SSE 流
│   ├── ChatService.swift     // SSE 解析器
│   ├── CalendarSyncService.swift  // EventKit 同步
│   ├── SpeechService.swift   // 语音转文字
│   └── LocationService.swift // CoreLocation
├── Stores/                   // @MainActor ObservableObject
│   ├── ChatStore.swift       // 消息持久化、每日会话重置
│   ├── PetStore.swift
│   ├── CalendarStore.swift
│   ├── DailyTaskStore.swift
│   ├── SubscriptionStore.swift
│   └── AuthStore.swift
├── Models/
│   └── ChatMessage.swift     // CardData 枚举（12 种卡片）
├── Theme/
│   ├── Tokens.swift          // 所有颜色/字体/间距/圆角
│   └── L.swift               // 双语字符串
└── Views/
    ├── Auth/      Login, Disclaimer, Onboarding
    ├── Chat/      ChatView, ChatInputBar, QuickActionCards, VoiceOverlay, SlashMenu
    ├── Calendar/  Drawer, MonthGrid, HeatStrip, Timeline (single/multi day), EventEdit, SpendingStats
    ├── Cards/     PlaceCard, PlaceDetailCard, DirectionsCard, ConfirmActionCard, DailyTaskCard, ReferencesCard, RecordCard, EmailCard
    ├── Settings/  Drawer, UserProfileSheet, PetFormView, PetProfileEditor, FamilySettingsView, PetShareSheet, PetUnshareSheet, QRScanner
    ├── DailyTasks/  DailyTaskManagerSheet
    ├── Paywall/   PaywallSheet, WhatsNewView
    └── Shared/    FullScreenImageViewer, PhotoCropSheet, CameraView, ShareSheet
```

**设计系统**：灵感来自 Timepage。所有 UI 使用 `Tokens.*`（颜色、字体、间距、圆角、组件尺寸），零硬编码值。调色：暖米色背景、橙色 accent、奶咖色文字、绿色正向确认、红色错误/紧急。

---

## 十一、关键设计决策

1. **纯聊天输入** — 没有表单、没有引导向导。产品原则：能让 AI 做的事，用户不做
2. **每日会话** — 每个自然日一个聊天 session，首条消息自动创建
3. **统一 ChatAgent** — 不做意图路由，一个 LLM 处理所有请求类型（聊天、记录、查询、紧急、导航），通过 function calling 决定动作
4. **Orchestrator + Executor** — LLM 决定做什么（function call），纯代码执行（DB 写入、API 调用）
5. **受约束 Agent** — 验证 + nudge + plan 追踪 + 后处理器兜底，让廉价模型也能可靠工作
6. **双模型路由** — 日常用便宜模型，紧急用准确模型；按关键词自动切换
7. **API 优先 iOS** — Store 先调后端，失败才 fallback 到 UserDefaults 缓存
8. **SSE 流式传输** — token 实时显示 + 结构化卡片，在同一个流中传递
9. **上下文惰性压缩** — 不塞 20 条原始消息，异步压缩成结构化摘要
10. **宠物档案异步提取** — 主对话不阻塞，profile_extractor 后台学习
11. **破坏性操作确认** — 删除类工具全部走确认卡片流程，永不直接执行
12. **Family plan = 情侣 mode** — Duo 订阅绑定宠物共享，解决两个人一起养的场景

---

## 十二、已知未完成项

- Phase 4 推送通知（基础设施已有，完整的提醒调度逻辑待完善）
- 知识库内容填充（RAG pipeline 已完成，但 knowledge 目录暂为空）
- iOS 端 References drawer 中的历史记录跳转到日历事件详情
- 生产环境安全加固：禁用 `/auth/dev` 端点、CORS 白名单审查
