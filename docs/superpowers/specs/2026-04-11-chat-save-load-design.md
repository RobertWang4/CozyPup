# 对话保存与加载 设计文档

## 概述

让用户可以保存优质对话、回看历史对话并继续聊天。通过 `/savechat` 和 `/loadchat` 两个 slash command 实现，同时支持从每日页回溯到特定日期的对话。切换对话时自动临时保存当前聊天（3天过期）。

---

## 一、数据模型

复用现有 `ChatSession`，新增 3 个字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_saved` | bool, default False | 永久保存标记 |
| `title` | str, nullable | AI 生成的标题（仅永久保存有） |
| `expires_at` | datetime, nullable | 临时保存的过期时间（3天后），永久保存为 NULL |

状态逻辑：
- `/savechat` → `is_saved=True`, `title=AI生成`, `expires_at=NULL`
- 自动临时保存 → `is_saved=False`, `title=NULL`, `expires_at=now+3天`
- 已永久保存的 session 不会被临时保存覆盖（永久优先）
- 查询时过滤：`WHERE is_saved=True OR (expires_at IS NOT NULL AND expires_at > now())`

---

## 二、Slash Commands

### `/savechat`

1. 用户输入 `/savechat`，弹出确认弹窗（参照 `/clear` 设计）
2. 用户点确认 → 调 `POST /api/v1/chat/sessions/{id}/save`
3. 后端设 `is_saved=True`，用轻量 LLM 调用（取最近 5 条消息）生成短标题（5-10字），存入 `title`
4. 弹窗显示 "已保存：{标题}" 后自动消失

### `/loadchat`

1. 用户输入 `/loadchat`，弹出半屏 sheet
2. 分两组展示：
   - 📌 **已保存** — `is_saved=True`，显示：标题 + 日期
   - 🕐 **最近对话** — `expires_at > now`，显示：日期 + 被替代时间点（如 "4/10 · 14:32被替代"）
3. 点击某条 → 进入只读聊天视图（显示历史消息，底部"继续对话"按钮）
4. 点"继续对话" → 当前对话自动临时保存 → 切换到选中的 session

---

## 三、自动保存与清理

### 切换对话时自动临时保存

- 触发：通过 `/loadchat` 或每日页回溯加载其他 session
- 行为：当前 session 设 `expires_at = now + 3天`
- 如果当前 session 已 `is_saved=True`，不覆盖

### 次日首次打开自动保存

- iOS 无后台定时任务，改为 `ChatStore.load()` 时检测
- 逻辑：检测到昨天的 session 且最后消息距今 > 30分钟 → 自动设 `expires_at = now + 3天` → 清空本地聊天
- 如果距今 ≤ 30分钟（跨夜聊天场景）→ 不操作

### 过期清理

- 查询时用 `expires_at IS NULL OR expires_at > now()` 过滤
- 不做物理删除，过期的仅不出现在列表中

---

## 四、API

```
POST /api/v1/chat/sessions/{id}/save
→ { "title": "AI生成的标题", "is_saved": true }
用 LLM 生成标题，设 is_saved=True，清除 expires_at

POST /api/v1/chat/sessions/{id}/temp-save
→ { "expires_at": "2026-04-14T...", "is_saved": false }
设 expires_at=now+3天（仅当 is_saved=False 时操作）

GET /api/v1/chat/sessions/saved
→ { "saved": [SessionItem], "recent": [SessionItem] }
saved: is_saved=True，按 session_date DESC
recent: expires_at > now 且 is_saved=False，按 expires_at DESC
SessionItem: { id, title, session_date, expires_at, is_saved, message_count }

POST /api/v1/chat/sessions/{id}/resume
→ { "session_id": "...", "messages": [ChatMessageResponse] }
返回该 session 的完整消息列表，供 iOS 加载到 ChatStore
```

标题生成：`/save` 端点用一次独立的轻量 LLM 调用（grok-4-1-fast），传入最近 5 条消息，prompt 为"用5-10个中文字概括这段对话的主题"。不走主聊天 pipeline。

---

## 五、iOS 界面

### SlashCommandMenu 扩展

在现有 SlashCommandMenu 中添加两项：
- `savechat` — 图标 `bookmark.fill`，标题"保存对话"
- `loadchat` — 图标 `clock.arrow.circlepath`，标题"加载对话"

### `/savechat` 弹窗

- 参照 `/clear` — Alert 确认框
- 确认 → loading → toast "已保存：{标题}" → 自动消失

### `/loadchat` Sheet

- 半屏 sheet（`.presentationDetents([.medium, .large])`）
- 两个 section：
  - 📌 已保存 — 每行：标题（左）+ 日期（右），`Tokens.fontBody` + `Tokens.fontCaption`
  - 🕐 最近对话 — 每行：日期（左）+ 替代时间（右，如 "14:32被替代"）
- 空状态：显示"还没有保存的对话"
- 点击行 → push 到只读聊天视图

### 只读聊天视图

- 复用 ChatView 的消息气泡渲染（ChatBubble），但无输入框
- 顶部：session 标题或日期
- 底部固定按钮："继续对话"（`Tokens.accent` 背景）
- 点击"继续对话" → 当前 session temp-save → 切换 ChatStore 到选中 session → 关闭 sheet

### 每日页回溯

- DailyTaskView 的日期区域加一个按钮（`clock.arrow.circlepath` 图标）
- 点击 → 打开 `/loadchat` 同一个 sheet

---

## 六、完整用户流程

```
场景 1：保存对话
  用户输入 /savechat
  → 弹窗确认
  → 后端 LLM 生成标题，设 is_saved=True
  → toast "已保存：豆豆疫苗咨询"

场景 2：加载对话
  用户输入 /loadchat
  → 半屏 sheet：已保存 + 最近对话
  → 点击"豆豆疫苗咨询 (4/8)"
  → 只读聊天视图，查看历史消息
  → 点"继续对话"
  → 当前对话自动 temp-save（3天过期）
  → 切换到 4/8 的 session，输入框可用

场景 3：每日页回溯
  用户在每日页点 4/9 的回溯按钮
  → 打开 /loadchat sheet
  → 定位到 4/9 的对话记录

场景 4：次日自动保存
  用户昨天聊了天，今天打开 app
  → ChatStore.load() 检测到昨天 session
  → 最后消息 > 30分钟前
  → 自动 temp-save 昨天 session（3天过期）
  → 清空本地，开始新的一天
```
