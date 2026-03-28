# Emergency 流程手动测试案例

## 目的
验证紧急情况从用户输入 → 后端检测 → SSE emergency 事件 → iOS 展示 EmergencyBanner 的完整链路。

---

## 前置条件
- 后端运行中（localhost:8000 或线上）
- iOS Simulator 已连接后端
- 至少有一只宠物

---

## 测试步骤

### Case 1: 真正的紧急情况 — 应触发 banner

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 打开 ChatView | 正常加载 |
| 2 | 输入「我的猫突然抽搐了！」发送 | ① AI 回复急救指导文字 ② 顶部出现红色 EmergencyBanner ③ Banner 显示 "Possible emergency detected" 和 "Find" 按钮 |
| 3 | 点击 "Find" 按钮 | Banner 消失（目前 onFind 只是 dismiss） |

### Case 2: 另一种紧急情况

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 输入「小维中毒了快死了」发送 | 同上：AI 急救回复 + EmergencyBanner |

### Case 3: 英文紧急情况

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 语言切换到 English | |
| 2 | 输入 "My dog is having seizures!" | AI 回复 first-aid guidance + EmergencyBanner |

### Case 4: 历史查询 — 不应触发

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 输入「上次中毒是什么时候」 | AI 正常回复，**没有** EmergencyBanner |

### Case 5: 轻微症状 — 不应触发

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 输入「小维今天有点打喷嚏」 | AI 正常回复，**没有** EmergencyBanner |

---

## 检查点

- [ ] Banner 在紧急情况下出现
- [ ] Banner 红色背景，有三角警告图标
- [ ] "Find" 按钮可点击
- [ ] "X" 按钮可关闭 Banner
- [ ] 非紧急消息不会误触发 Banner
- [ ] AI 文字回复中包含急救建议（不只是 Banner）

---

## 已知问题

1. **EmergencyBanner 未使用 EmergencyData 内容**
   - `message` 和 `action` 字段被忽略，Banner 显示硬编码文字
   - `onFind` 只是关闭 Banner，没有跳转到找医院
   - 建议后续：用 `action` 字段决定行为（find_er → 搜附近急诊，call_vet → 拨号，first_aid → 展示急救步骤）

2. **Emergency model 不可用**
   - `.env` 中 `EMERGENCY_MODEL=openai/codex-gpt-5.4` 通过代理报错
   - 临时方案：改为和普通 model 一样的值
