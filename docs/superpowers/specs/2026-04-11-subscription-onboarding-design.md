# CozyPup 订阅付费 & 新用户引导 设计文档

## 概述

CozyPup 采用纯订阅制，7 天免费试用，试用期间软弹付费墙引导，到期后数据回顾型付费墙 + 只读模式。同时新增首次使用引导（AI 欢迎 + 快捷卡片 + placeholder 轮播）解决冷启动问题。

---

## 一、新用户引导

### 1.1 AI 欢迎消息（仅首次）

用户第一次进入聊天页面时，前端硬编码一条 AI 消息（不经过 LLM）：

> 🐾 你好！我是 CozyPup，你的宠物专属管家。
>
> 我可以帮你：记录健康状况、设置疫苗提醒、查找附近宠物医院、解答养宠问题。
>
> 先告诉我你家毛孩子叫什么吧～

- 使用 `UserDefaults` 存储 `has_seen_welcome` flag
- 消息样式与普通 AI 消息一致（使用 `Tokens.bubbleAi`）
- 只触发一次，后续登录不再显示

### 1.2 快捷卡片（每天空 session）

每天新 session、聊天记录为空时，在聊天区中部展示 4 个可点击卡片：

| 卡片 | 图标 | 点击后发送的消息 |
|------|------|----------------|
| 添加宠物 | 🐶 | "我想添加一只宠物" |
| 健康咨询 | 💊 | "我家宠物最近有点不舒服" |
| 设个提醒 | 📅 | "帮我设一个提醒" |
| 附近医院 | 📍 | "帮我找附近的宠物医院" |

行为：
- 2x2 网格布局，位于聊天区中部
- 点击卡片 → 将对应文字填入输入框并自动发送
- 用户发出任何消息后（包括点卡片触发的），卡片消失
- 使用 `Tokens.surface` 背景，`Tokens.radiusSmall` 圆角

### 1.3 Placeholder 轮播（始终）

输入框 placeholder 每 4 秒淡入淡出切换：

1. "试试说：我家狗最近老挠耳朵…"
2. "试试说：帮我记一下今天打了疫苗"
3. "试试说：下周三提醒我去宠物店"

- 始终存在，不受首次/非首次影响
- 用户开始输入后 placeholder 消失（系统默认行为）

---

## 二、订阅付费体系

### 2.1 订阅模型

- **计费方式**：纯订阅（月付 / 年付），价格待定
- **免费试用**：7 天，注册即开始，不需预先绑定支付方式
- **技术栈**：StoreKit 2（iOS 17+）

### 2.2 数据模型变更

User 模型新增字段：

```python
subscription_status: str  # "trial" | "active" | "expired"
trial_start_date: datetime  # 注册时自动设置
subscription_expires_at: datetime | None  # 订阅到期时间
subscription_product_id: str | None  # App Store 产品 ID
```

新增后端统计查询（用于数据回顾型付费墙）：

```python
# 试用期内的使用统计
GET /api/v1/subscription/trial-stats
→ { "chat_count": 23, "reminder_count": 4, "event_count": 8 }
```

### 2.3 订阅状态判断

后端中间件在每次请求时检查用户订阅状态：

```
if subscription_status == "trial":
    if now > trial_start_date + 7 days:
        subscription_status = "expired"  # 自动过期
    else:
        allow  # 试用期内，正常使用

if subscription_status == "active":
    if now > subscription_expires_at:
        subscription_status = "expired"
    else:
        allow

if subscription_status == "expired":
    if request is read-only (GET):
        allow
    else:
        return 403 { "code": "subscription_expired" }
```

### 2.4 iOS 端订阅状态管理

新建 `SubscriptionStore`（`@MainActor ObservableObject`）：

- 启动时从 StoreKit 2 检查当前订阅状态
- 监听 `Transaction.updates` 处理续费/取消/过期
- 暴露 `status: SubscriptionStatus` 枚举（`.trial(daysLeft)` / `.active` / `.expired`）
- 暴露 `purchase(product:)` 方法调用 StoreKit 购买
- 暴露 `restorePurchases()` 方法

### 2.5 App Store 产品配置

两个自动续期订阅产品（需在 App Store Connect 配置）：

| 产品 ID | 类型 | 价格 |
|---------|------|------|
| `com.cozypup.app.monthly` | 月付自动续期 | 待定 |
| `com.cozypup.app.yearly` | 年付自动续期 | 待定 |

同一订阅组，App Store 自动处理升降级。

---

## 三、付费墙界面

### 3.1 软弹付费墙（试用期内）

**触发条件**：累计发送 ≥ 10 条消息 **且** 注册超过 24 小时（取交集）

**行为**：
- 半屏 sheet 弹出（`.presentationDetents([.medium])`）
- 右上角关闭按钮，可关闭
- 关闭后本次 session 不再弹出
- 整个试用期最多弹 2 次（首次满足条件时 + 到期前一天）
- 使用 `UserDefaults` 记录弹出次数和日期

**内容**：
- 标题："喜欢 CozyPup 吗？"
- 副标题："试用还剩 X 天"
- 权益列表（3 项）：无限 AI 对话、智能提醒 & 日历管理、附近宠物医院搜索
- CTA 按钮："查看方案" → 当前 sheet 内切换到月/年价格选择视图（复用到期付费墙的底部定价卡片布局）
- 次要链接："暂不需要" → 关闭

### 3.2 到期付费墙（数据回顾型）

**触发条件**：`subscription_status == "expired"` 时打开 app

**行为**：
- 半屏 sheet 弹出，**不可关闭**（无关闭按钮，`interactiveDismissDisabled(true)`）
- 关闭 app 再打开仍然弹出
- 从设置页也可手动打开

**内容**：
- 标题："这 7 天，CozyPup 帮你"
- 使用数据（从 `/subscription/trial-stats` 获取）：
  - 对话次数（accent 色 `E8835C`）
  - 提醒数量（蓝色 `6BA3BE`）
  - 记录数量（绿色 `7BAE7F`）
- 情感文案："继续让 CozyPup 照顾你的毛孩子 🐶"
- 月/年双卡片价格对比，年付高亮 + "推荐" badge
- CTA 按钮："订阅"
- 底部小字："恢复购买"

### 3.3 只读模式

到期后关闭付费墙（仅当从设置页入口打开时可关闭），进入只读模式：

- **可用**：浏览历史聊天、查看日历事件、查看宠物档案
- **禁用**：
  - 聊天输入框禁用，placeholder 显示 "订阅后继续对话"
  - 点击日历的添加/编辑按钮 → 弹出到期付费墙
  - 点击任何创建/修改操作 → 弹出到期付费墙
- **设置页**：显示 "会员已过期" 状态 + "续费" 按钮入口

---

## 四、后端接口

### 4.1 新增 API

```
GET  /api/v1/subscription/status
→ { "status": "trial|active|expired", "trial_days_left": 5, "expires_at": "..." }

GET  /api/v1/subscription/trial-stats
→ { "chat_count": 23, "reminder_count": 4, "event_count": 8 }

POST /api/v1/subscription/verify
← { "transaction_id": "...", "product_id": "..." }
→ { "status": "active", "expires_at": "..." }
```

### 4.2 App Store Server Notifications V2

- 后端新增 webhook endpoint：`POST /api/v1/subscription/webhook`
- 处理事件：`SUBSCRIBED`、`DID_RENEW`、`EXPIRED`、`DID_REVOKE`、`GRACE_PERIOD_EXPIRED`
- 更新 User 的 `subscription_status` 和 `subscription_expires_at`

### 4.3 写操作拦截

新增中间件或依赖，对 `subscription_status == "expired"` 的用户：
- `GET` 请求放行
- `POST` / `PUT` / `PATCH` / `DELETE` 请求返回 `403 { "code": "subscription_expired" }`
- 排除的路径：`/auth/*`、`/subscription/*`（允许过期用户登录和购买）

---

## 五、用户旅程完整流程

```
注册登录
  → 后端设置 subscription_status = "trial", trial_start_date = now
  → 首次进入聊天
  → AI 主动欢迎消息 + 快捷卡片展示
  → 用户开始使用（聊天、建档、设提醒…）
  → 10条消息 + 24小时后，软弹付费墙（可关闭）
  → 继续免费用到第7天
  → 到期前一天，第二次软弹付费墙
  → 第7天到期
    → 打开 app：弹数据回顾型付费墙（不可关闭）
    → 付费 → subscription_status = "active" → 正常使用
    → 不付费 → subscription_status = "expired" → 只读模式
```

---

## 六、技术要点

- **StoreKit 2**：使用 `Product.products(for:)` 获取产品，`product.purchase()` 购买，`Transaction.currentEntitlements` 检查状态
- **后端验证**：依赖 App Store Server Notifications V2 webhook，不做客户端收据验证
- **状态同步**：iOS 端启动时查 StoreKit 本地状态 + 调 `/subscription/status` 双重校验
- **新用户默认值**：注册时 `subscription_status = "trial"`，现有用户迁移时设为 `"active"`（不影响老用户）
