# Daily Tasks (每日待办) Design Spec

## Overview

为宠物主人提供每日待办 checklist 功能。支持常规待办（每天遛狗2次）和特殊待办（接下来7天每天吃益生菌）。通过聊天页置顶小图标 + 浮窗交互，日历页管理入口，AI 对话创建/编辑/删除。

## 数据模型

### daily_tasks 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| user_id | UUID FK → users | 所属用户 |
| pet_id | UUID FK → pets, nullable | 关联宠物（可选） |
| title | String(200) | "遛狗"、"吃益生菌" |
| type | Enum: routine / special | 常规（永久）or 特殊（有起止日期） |
| daily_target | int, default 1 | 每天需完成次数 |
| start_date | Date, nullable | 特殊待办开始日期，常规为 null（立即生效） |
| end_date | Date, nullable | 特殊待办结束日期，常规为 null（永久） |
| active | bool, default True | 常规待办关闭时设 False |
| created_at | DateTime | |

### daily_task_completions 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| task_id | UUID FK → daily_tasks, CASCADE | |
| date | Date | 哪天的记录 |
| count | int, default 0 | 当天已完成次数 |
| unique constraint | (task_id, date) | 每任务每天一条 |

**完成状态逻辑：**
- 用户点击一次 → count +1（如 0/2 → 1/2）
- 达到 target → 该任务当天完成
- 没有 completion 记录 = 0/target（未开始）
- completion 记录保留 7 天，后台定期清理超过 7 天的记录
- AI 对话时可查最近 7 天完成情况（如"豆豆上周益生菌吃了几天？"）

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/tasks/today` | 今日待办列表（含 count/target） |
| POST | `/api/v1/tasks` | 创建待办 |
| PUT | `/api/v1/tasks/{id}` | 修改待办 |
| DELETE | `/api/v1/tasks/{id}` | 删除待办 |
| POST | `/api/v1/tasks/{id}/tap` | 完成一次（count +1） |

### GET /tasks/today 逻辑

查询所有 `active=True` 且在日期范围内的 daily_tasks（常规：active=True；特殊：start_date <= today <= end_date），LEFT JOIN 当天的 completion 记录。返回：

```json
{
  "tasks": [
    {
      "id": "uuid",
      "title": "遛狗",
      "type": "routine",
      "daily_target": 2,
      "completed_count": 1,
      "pet": { "id": "uuid", "name": "豆豆", "color_hex": "E8835C" }
    }
  ],
  "all_completed": false
}
```

### POST /tasks/{id}/tap 逻辑

- 如果当天没有 completion 记录 → 创建一条 count=1
- 如果已有记录且 count < target → count +1
- 如果 count >= target → 忽略（已完成）
- 返回更新后的 count 和 all_completed 状态

## Agent Tools

### create_daily_task

通过对话创建待办。

```json
{
  "name": "create_daily_task",
  "parameters": {
    "title": "遛狗",
    "type": "routine",
    "daily_target": 2,
    "pet_id": "uuid (optional)",
    "start_date": "2026-03-28 (special only)",
    "end_date": "2026-04-03 (special only)"
  }
}
```

示例触发：
- "帮我设置每天遛狗两次" → routine, target=2
- "接下来一周提醒我每天给狗狗吃益生菌" → special, target=1, start/end 7天

### manage_daily_task

通过对话编辑/删除待办。

```json
{
  "name": "manage_daily_task",
  "parameters": {
    "action": "update | delete | deactivate",
    "task_id": "uuid (if known)",
    "title": "遛狗 (用于模糊匹配找到任务)",
    "updates": {
      "title": "new title",
      "daily_target": 3,
      "end_date": "2026-04-10"
    }
  }
}
```

示例触发：
- "把遛狗改成三次" → action=update, title="遛狗", updates={daily_target: 3}
- "取消益生菌的待办" → action=delete, title="益生菌"
- "暂停遛狗的待办" → action=deactivate, title="遛狗"

**模糊匹配逻辑**：当 task_id 未提供时，用 title 关键词在用户的 active 待办中模糊搜索。如果匹配到多个，返回列表让 AI 追问用户。

## iOS 交互

### 聊天页 — 置顶待办指示器

- 聊天消息列表顶部固定一个小圆圈对勾图标（`Tokens.size.buttonSmall` 36pt）
- 状态颜色：未全部完成 → `Tokens.textSecondary`，全部完成 → `Tokens.green`
- 没有今日待办时不显示图标
- 点击 → 弹出浮窗

### 待办浮窗（聊天页）

- 约 1/3 屏幕高度，浮在聊天上方，不遮挡输入框
- 圆角卡片样式（`Tokens.radius`），背景 `Tokens.surface`
- 内容：待办列表，每行：
  - 标题文字（`Tokens.fontBody`）
  - 宠物标签（如关联了宠物）：小圆角标签，宠物 color_hex 背景 + 宠物名字（`Tokens.fontCaption`）
  - 进度区：点击按钮 + 文字（如 "1/2"）
  - 点击按钮 → 调 POST /tap → count +1 → UI 即时更新
  - 达到 target → 该行变为完成态（绿色勾 + 文字变灰）
- 全部完成 → 顶部圆圈变绿
- 点击浮窗外部关闭

### 日历页 — 待办管理入口

- 日历页放一个同样的圆圈对勾图标
- 点击 → 从底部上滑弹窗（`.sheet` 或自定义 half-sheet）
- 弹窗内容：管理待办
  - 列出所有待办（常规 + 进行中的特殊）
  - 每项可编辑（标题、频次、日期）、删除、停用
  - 底部"添加待办"按钮 → 新建表单（选择常规/特殊、关联宠物、设频次）

## 推送通知（暂不实现）

设计预留，等 Apple Developer Account 激活后实现：

- 每天早上 8:00 检查是否有未完成的今日待办
- 如有 → 推送通知："今日还有 N 项待办未完成"
- 后端需要：定时任务（cron）+ 推送服务（APNs）
- 接口预留：daily_tasks 表已包含所有需要的数据，无需额外字段

## 不做的事

- 不做待办完成的历史统计页面（7天后数据清理）
- 不做 AI 查看待办的 tool（用户点击即可看到）
- 不做待办排序/优先级
- 不做待办分类/标签（宠物标签已足够）
