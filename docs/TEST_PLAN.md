# CozyPup 端到端测试计划

> 更新日期：2026-04-15
> 覆盖范围：全部 33 个工具 + 所有用户交互场景
> 测试方式：E2E 自动化（`tests/e2e/`），输入用户消息 → 验证 SSE 输出 + 工具调用 + DB 副作用
> 图片测试：使用 `Photos/resized/` 目录下的 PNG 文件，base64 编码后通过 `images` 参数发送

## 运行方式

```bash
# 启动后端
cd backend && uvicorn app.main:app --reload --port 8000

# 完整 E2E audit（含 debug trace）
python tests/e2e/run_audit.py --lang zh
python tests/e2e/run_audit.py --lang en

# 单个用例
python tests/e2e/run_audit.py --lang zh --case 2.1

# pytest E2E（更细粒度的断言）
pytest tests/e2e/ -v --tb=short

# 图片测试需要真实图片 base64，helper 函数：
# from tests.e2e.conftest import load_test_image
# img_b64 = load_test_image("Photos/resized/IMG_1025.PNG")
```

## 验证维度

每个用例验证以下维度（按适用性）：

| 维度 | 说明 | 验证方式 |
|------|------|----------|
| **工具调用** | LLM 是否调了正确的工具 | `_get_tools_called(result)` 从 debug trace 提取 |
| **卡片输出** | SSE 流中是否返回了正确类型的卡片 | `result.has_card(type)`, `result.first_card(type)` |
| **卡片字段** | 卡片中的数据是否正确 | `card["category"]`, `card["date"]`, `card["cost"]` 等 |
| **文本回复** | LLM 回复文本是否符合预期 | `result.text` 内容检查、语言检查 |
| **DB 副作用** | 数据库是否正确写入/更新/删除 | `get_pets()`, `get_events()`, `get_tasks()` API 验证 |
| **紧急事件** | SSE event type 是否为 emergency | `result.emergency` 非空检查 |
| **否定验证** | 不该发生的事没有发生 | 无卡片、无紧急、无特定工具调用 |

---

## 1. 基础聊天

| # | 输入 | 预期输出 | 工具调用 | 验证 |
|---|------|---------|---------|------|
| 1.1 | "你好" | 温暖的问候回复 | 无 | `text` 非空，无 card |
| 1.2 | "hi"（lang=zh） | 中文回复 | 无 | `has_cjk(text)` == True |
| 1.3 | "hi"（lang=en） | 英文回复 | 无 | `text` 非空，无 CJK 字符 |
| 1.4 | 连续发 3 条闲聊 | 每条都正常回复，session 保持 | 无 | 3 条 `text` 均非空，`session_id` 一致 |
| 1.5 | "你能做什么？" | 介绍产品功能 | `introduce_product` | `"introduce_product" in tools_called` |
| 1.6 | "how to use this app" | 英文功能介绍 | `introduce_product` | `"introduce_product" in tools_called` |

---

## 2. 创建日历事件（create_calendar_event）

### 2a. 基础记录

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 2.1 | "小维今天吃了狗粮" | record 卡片 | `card["category"]=="diet"`, `card["date"]==today` |
| 2.2 | "昨天去公园散步了" | record 卡片 | `card["category"]=="daily"`, `card["date"]==yesterday` |
| 2.3 | "上周五打了疫苗" | record 卡片 | `card["category"]=="medical"`, date 为上周五 |
| 2.4 | "上周带小维去了医院" | 追问具体日期 | 无 record 卡片，回复含 `?` |
| 2.5 | "3月20号做了体检" | record 卡片 | `card["category"]=="medical"`, `card["date"]` 含 "03-20" |
| 2.6 | "小维吐了" | record 卡片 | `card["category"]=="abnormal"` |
| 2.7 | "小维拉肚子了" | record 卡片 | `card["category"]=="abnormal"` |
| 2.8 | "今天做了驱虫" | record 卡片 | `card["category"]=="medical"` |
| 2.9 | "小维今天游泳了" | record 卡片 | `card["category"]=="daily"` |

### 2b. 多事件拆分（plan 工具）

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 2.10 | "今天遛了狗还洗了澡" | ≥2 个 record 卡片 | `card_count("record") >= 2` |
| 2.11 | "记录吃狗粮，提醒打疫苗" | record 卡片 + reminder 卡片 | `has_card("record")` 且 `has_card("reminder")` |
| 2.12 | "遛了狗、喂了狗粮、洗了澡" | ≥3 个 record 卡片 | `card_count("record") >= 3` |

### 2c. 花费记录

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 2.13 | "带小维去医院花了300" | record 卡片 cost=300 | `card["cost"] == 300` |
| 2.14 | "洗澡花了80块" | record 卡片 cost=80 | `card["cost"] == 80` |
| 2.15 | "小维今天吃了狗粮"（无花费） | record 卡片 cost=None | `card["cost"] is None` |
| 2.16 | "体检花了1500" | record 卡片 cost=1500 | `card["cost"] == 1500` |
| 2.17 | "遛狗途中买了零食50块"（多事件+花费） | ≥2 record，零食那条 cost=50 | 遛狗 cost=None，零食 cost=50 |

### 2d. 提醒时间（reminder_at 参数）

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 2.18 | "明天下午3点带小维去打疫苗，提醒我" | record 卡片 + reminder_at | `card["reminder_at"]` 含明天日期 |
| 2.19 | "下周二体检别忘了" | record 卡片 | `card["date"]` 为下周二 |

---

## 3. 查询事件（query_calendar_events）

| # | setup（前置消息） | 输入 | 预期输出 | 验证 |
|---|-----------------|------|---------|------|
| 3.1 | "小维今天打了疫苗" | "小维上次打疫苗是什么时候？" | 回复含疫苗记录 | `text` 含 "vaccin"/"疫苗" |
| 3.2 | "小维今天吃了狗粮" | "这周记录了什么？" | 回复列出本周事件 | `text` 非空 |
| 3.3 | "小维今天吃了狗粮" | "小维最近吃了什么？" | 回复含饮食记录 | `text` 含 "食"/"food"/"eat" |
| 3.4 | 创建花费记录 | "最近花了多少钱？" | 回复含花费金额 | `text` 含数字金额 |

---

## 4. 修改/删除事件

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 4.1 | "小维今天打疫苗了" | "刚才那条记录日期不对，应该是3月25号" | 日期更新 | `get_events("2026-03-25")` 有记录 |
| 4.2 | "小维昨天散步了" | "删掉昨天的散步记录" | confirm_action 卡片 | `has_card("confirm_action")` |
| 4.3 | 4.2 + 点确认 | `confirm_action(action_id)` | 事件被删除 | `get_events(yesterday)` 数量减少 |
| 4.4 | "小维今天散步了" | "把标题改成'公园散步'" | 标题更新 | `get_events(today)` 标题含 "公园" |
| 4.5 | "小维今天体检花了500" | "其实花了800" | cost 更新 | `get_events(today)` cost==800 |

---

## 5. 宠物管理

### 5a. 创建宠物（create_pet）

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 5.1 | "我新养了一只猫叫花花" | pet_created 卡片 | `card["species"]=="cat"`, `get_pets()` 含 "花花" |
| 5.2 | "I just got a new puppy named Buddy" | pet_created 卡片 | `card["species"]=="dog"`, `get_pets()` 含 "Buddy" |

### 5b. 更新宠物信息（update_pet_profile）

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 5.3 | 有花花 | "花花是母的" | 性别更新（可能需确认） | `get_pets()` gender 非空 |
| 5.4 | 5.3 后 | "花花其实是公的" | 拒绝（性别锁定） | 回复含 "锁定"/"locked" |
| 5.5 | 有花花 | "花花体重5公斤" | pet_updated 卡片 | `get_pets()` weight≈5.0 |
| 5.6 | 有花花 | "花花生日是2024年3月5号" | pet_updated 卡片 | `get_pets()` birthday 含 "2024-03-05" |
| 5.7 | 有花花 | "花花对鸡肉过敏" | profile 更新 | `get_pets()` profile 含 "鸡肉"/"chicken" |
| 5.8 | 有花花 | "把花花名字改成咪咪" | pet_updated 卡片 | `get_pets()` 有 "咪咪"，无 "花花" |

### 5c. 防重复 & 删除

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 5.9 | 有小维 | "我养了一只新狗叫小维" | 不创建重复 | 宠物数不增加 |
| 5.10 | 有花花 | "删掉花花" | confirm_action 卡片 | `has_card("confirm_action")`，确认后宠物消失 |

### 5d. 列出宠物（list_pets）

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 5.11 | 有小维+花花 | "我有几只宠物？" | 回复列出所有宠物 | `text` 含两只宠物名字 |

---

## 6. 宠物头像（set_pet_avatar）

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 6.1 | 发图片 + "用这个当小维的头像" | 头像更新 | `"set_pet_avatar" in tools_called`，`get_pets()` avatar_url 非空 |
| 6.2 | 发图片 + "这是小维" | 追问用户意图 | 回复含 `?`（问要做什么） |

---

## 7. 照片上传（upload_event_photo + request_images）

### 7a. 当前 turn 发图 + 创建事件（图片自动附加）

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 7.1 | 发图片 + "记录一下小维今天" | record 卡片 | `has_card("record")`，`get_events(today)` photos 非空 |
| 7.2 | 发2张图片 + "记一下" | record 卡片 | `get_events(today)` photos 长度 ≥2 |

### 7b. 追加照片到已有事件（upload_event_photo）

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 7.3 | "小维今天去公园了" | 发图片 + "把这张照片加到刚才的记录" | 调 upload_event_photo | `"upload_event_photo" in tools_called`，`get_events(today)` photos 非空 |
| 7.4 | "小维今天去公园了" | 发图片 + "Add this to the event" | 同上 | 同上 |

### 7c. 跨 turn 图片回退（recent_image_urls）

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 7.5 | 发图片 + "小维今天去公园了"（agent 未记录） | "记录一下"（无图片） | 记录事件 + 附带之前的图片 | `get_events(today)` photos 非空 |
| 7.6 | 发图片 + "小维真可爱" | "刚才那张照片是什么品种？"（无图片） | 调 request_images 从历史读取 | `"request_images" in tools_called`，`text` 含品种信息 |

### 7d. 图片 vision 分析（request_images）

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 7.7 | 发图片 + "这是什么品种？" | LLM 分析图片内容回答 | `"request_images" in tools_called`，`text` 非空 |
| 7.8 | 发图片 + "看看这只狗有什么问题吗？" | 图片分析 + search_knowledge | `"request_images" in tools_called` |

### 7e. 删除事件照片（remove_event_photo）

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 7.9 | 创建带图事件 | "把那条记录的照片删掉" | 照片被删除 | `"remove_event_photo" in tools_called`，`get_events()` photos 为空 |

---

## 8. 每日待办（create_daily_task / list_daily_tasks / manage_daily_task）

### 8a. 创建待办

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 8.1 | "每天提醒我遛狗" | daily_task_created 卡片 | `card["task_type"]=="routine"`，无 end_date |
| 8.2 | "这周每天给小维量体温" | daily_task_created 卡片 | `card["task_type"]=="special"`，有 end_date |
| 8.3 | "每天喂两次药" | daily_task_created 卡片 | `card["daily_target"]==2` |

### 8b. 查询待办

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 8.4 | 创建遛狗待办 | "我有什么待办？" | 回复列出待办 | `"list_daily_tasks" in tools_called`，`text` 含 "遛狗" |
| 8.5 | 无待办 | "我有什么待办？" | 回复说没有 | `"list_daily_tasks" in tools_called` |

### 8c. 管理待办

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 8.6 | 创建遛狗待办 | "取消遛狗任务" | confirm_action 卡片 | `has_card("confirm_action")` |
| 8.7 | 创建多个待办 | "删除所有待办" | confirm_action 卡片 | `has_card("confirm_action")`，确认后待办清空 |
| 8.8 | 创建遛狗待办 | "把遛狗改成每天2次" | daily_task_updated 卡片 | 待办 daily_target 更新 |

---

## 9. 提醒（create_reminder / list / update / delete）

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 9.1 | "提醒我明天给小维喂药" | reminder 卡片 | `has_card("reminder")`，trigger_at 含明天 |
| 9.2 | "下周二带小维去打疫苗别忘了" | reminder 卡片 | `has_card("reminder")` |
| 9.3 | "我有什么提醒？" | 列出提醒 | `"list_reminders" in tools_called` |
| 9.4 | "改成后天下午3点" | 更新提醒 | `"update_reminder" in tools_called` |
| 9.5 | "取消明天的喂药提醒" | confirm_action 卡片 | `has_card("confirm_action")` |
| 9.6 | "取消所有提醒" | confirm_action 卡片 | `has_card("confirm_action")`，确认后提醒清空 |

---

## 10. 地点搜索（search_places / search_places_text / get_place_details / get_directions）

所有地点测试需带 `location={"lat": 45.4215, "lng": -75.6972}`。

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 10.1 | — | "附近有宠物医院吗" | place_card 卡片 | `has_card("place_card")` |
| 10.2 | — | "帮我找最近的狗公园" | place_card 卡片 | `has_card("place_card")` |
| 10.3 | — | "北京朝阳区宠物医院" | place_card 卡片 | `"search_places_text" in tools_called` |
| 10.4 | 10.1 后 | "第一家评价怎么样？" | place_detail 卡片 | `has_card("place_detail")` |
| 10.5 | 10.1 后 | "怎么去那里？" | directions 卡片 | `has_card("directions")` |
| 10.6 | — | "Find a vet near me" | place_card 卡片 | `has_card("place_card")` |

### 10b. 事件关联地点（add_event_location）

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 10.7 | "小维今天去公园了" | "就是在 Central Park" | 地点关联到事件 | `"add_event_location" in tools_called`，`get_events(today)` location 非空 |
| 10.8 | — | "带小维去了 Vanier Animal Hospital 做体检" | 创建事件 + 关联地点 | `has_card("record")`，event.location 非空 |

---

## 11. 邮件草拟（draft_email）

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 11.1 | "帮我写一封邮件给兽医说明小维最近皮肤过敏" | email 卡片 | `has_card("email")`，card 含 subject + body |
| 11.2 | "Draft an email to the vet about Weiwei's vaccination history" | email 卡片 | `has_card("email")` |

---

## 12. 紧急情况（trigger_emergency）

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 12.1 | "我的猫突然抽搐了！" | emergency SSE 事件 | `result.emergency` 非空，`emergency["action"]` 在 `{find_er, call_vet, first_aid}` |
| 12.2 | "小维中毒了快死了" | emergency SSE 事件 | `result.emergency` 非空 |
| 12.3 | "小维呼吸困难！" | emergency SSE 事件 | `result.emergency` 非空 |
| 12.4 | "My dog is having seizures!" | emergency SSE 事件 | `result.emergency` 非空 |
| 12.5 | "上次中毒是什么时候" | **不触发**紧急 | `result.emergency` 为空 |
| 12.6 | "小维以前抽搐过吗？" | **不触发**紧急 | `result.emergency` 为空 |

---

## 13. 语言切换（set_language）

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 13.1 | "switch to English" | set_language(en) | `"set_language" in tools_called` |
| 13.2 | "切换成中文" | set_language(zh) | `"set_language" in tools_called` |
| 13.3 | "说英文" | set_language(en) | `"set_language" in tools_called` |
| 13.4 | "speak Chinese" | set_language(zh) | `"set_language" in tools_called` |

---

## 14. 多宠物场景

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 14.1 | 2只宠物 | "吃了狗粮"（不说名字） | 追问哪只 | 回复含 `?` 或列出宠物 |
| 14.2 | 2只宠物 | "小维和花花一起散步了" | 事件关联两只 | `has_card("record")` |
| 14.3 | 1只宠物 | "吃了狗粮" | 自动关联唯一宠物 | `has_card("record")`，card 含 pet_name |
| 14.4 | 2只宠物 | "小维吃了狗粮" | 只关联小维 | record 卡片 pet_name 仅含 "小维" |
| 14.5 | 2只宠物 | "花花吐了" | 只关联花花 | record 卡片 pet_name 仅含 "花花" |

---

## 15. 档案管理（save_pet_profile_md / summarize_pet_profile）

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 15.1 | 有小维 | "小维很怕打雷，性格胆小" | profile_md 更新 | `get_pets()` profile_md 含 "怕打雷"/"性格" |
| 15.2 | 15.1 后 | "帮我总结一下小维的档案" | 调 summarize_pet_profile | `"summarize_pet_profile" in tools_called`，`text` 含档案内容 |
| 15.3 | 多轮对话补充信息 | 检查 profile_md | 后台 profile_extractor 异步更新 | `get_pets()` profile_md 含所有提到的信息 |

---

## 16. 健康知识问答（search_knowledge / RAG）

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 16.1 | "小维呕吐了怎么办" | 调 search_knowledge + 回复建议 | `"search_knowledge" in tools_called`，`text` 非空 |
| 16.2 | "小维最近老是拉肚子" | 调 search_knowledge | `"search_knowledge" in tools_called` |
| 16.3 | "My dog has been vomiting, what should I do?" | 调 search_knowledge | `"search_knowledge" in tools_called` |
| 16.4 | "帮我记录小维今天吃了狗粮" | **不调** search_knowledge | `"search_knowledge" not in tools_called`，`has_card("record")` |

### 16b. 图片 + 健康问答

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 16.5 | 发图片 + "小维皮肤上有红点，什么情况？" | request_images + search_knowledge | 两个工具都被调用 |

---

## 17. 上下文压缩（context_agent）

| # | 操作 | 预期输出 | 验证 |
|---|------|---------|------|
| 17.1 | 发 7+ 条消息，然后问"小维最近怎么样？" | 回复引用之前的对话内容 | `text` 非空，含前几条消息的相关信息 |
| 17.2 | 发 7+ 条消息，检查 session.context_summary | 后台压缩完成 | context_summary 非空（需 API 验证） |

---

## 18. 日历同步（sync_calendar）

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 18.1 | "帮我同步到手机日历" | 调 sync_calendar | `"sync_calendar" in tools_called` |

---

## 19. 多步规划（plan 工具）

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 19.1 | "今天遛了狗还洗了澡" | plan 拆分 + 2个 record 卡片 | `card_count("record") >= 2` |
| 19.2 | "记录吃狗粮，提醒明天打疫苗" | plan 拆分 + record + reminder | `has_card("record")` 且 `has_card("reminder")` |
| 19.3 | "遛了狗、喂了猫、给花花洗澡"（2只宠物） | ≥3 个 record 卡片 | `card_count("record") >= 3` |

---

## 20. 确认门控（破坏性操作）

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 20.1 | 有小维 | "删掉小维" | confirm_action 卡片 | `has_card("confirm_action")`，card 含描述 |
| 20.2 | 有事件 | "删掉今天的记录" | confirm_action 卡片 | `has_card("confirm_action")` |
| 20.3 | 有提醒 | "取消这个提醒" | confirm_action 卡片 | `has_card("confirm_action")` |
| 20.4 | 有待办 | "删除遛狗待办" | confirm_action 卡片 | `has_card("confirm_action")` |
| 20.5 | 20.1 | 点击确认 | 宠物被删除 | `confirm_action()` 成功，`get_pets()` 无该宠物 |
| 20.6 | 20.1 | 不点击（超时） | 动作过期 | 1小时后 confirm 返回失败 |

---

## 21. 边界场景

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 21.1 | 无宠物 | "你好" | 正常回复 | `text` 非空，不报错 |
| 21.2 | 有宠物无事件 | "小维最近怎么样？" | 回复说没有记录 | `text` 非空 |
| 21.3 | — | 发超长消息（500+ 字） | 正常处理 | `text` 非空，无 error |
| 21.4 | — | 发空消息 "" | 错误提示 | 不 crash |
| 21.5 | — | "记录吃狗粮"（无宠物） | 提示先创建宠物或自动创建 | 有合理回复 |

---

## 22. i18n 语言一致性

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 22.1 | lang=en | "Delete all daily tasks" | 英文 confirm 描述 | confirm card 描述不含 CJK |
| 22.2 | lang=en | Create event then "Delete it" | 英文 confirm 描述 | confirm card 描述不含 CJK |
| 22.3 | lang=zh | "删除所有待办" | 中文 confirm 描述 | confirm card 描述含 CJK |
| 22.4 | lang=en, 创建待办后删除 | daily_task_deleted 卡片 | 卡片 title 为英文 | `card["title"]` 不含 CJK |
| 22.5 | lang=zh, 创建待办后删除 | daily_task_deleted 卡片 | 卡片 title 为中文 | `card["title"]` 含 CJK |

---

## 23. Nudge 机制（预处理器 + 催促）

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 23.1 | "附近有宠物医院吗"（带 location） | 调 search_places | `"search_places" in tools_called`（不能只回文字） |
| 23.2 | "switch to English" | 调 set_language | `"set_language" in tools_called`（不能只换语言回复） |
| 23.3 | "小维中毒了！" | 调 trigger_emergency | `result.emergency` 非空（不能只给文字建议） |

---

## 24. 修正记录

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 24.1 | "小维今天打了疫苗" | "日期不对，应该是3月25号" | update_calendar_event | `"update_calendar_event" in tools_called`，不创建新事件 |
| 24.2 | "小维今天吃了狗粮" | "分类应该是 medical 不是 diet" | update_calendar_event | event.category 更新 |
| 24.3 | "小维今天散步了" | "改成'公园散步'" | update_calendar_event | event.title 更新 |

---

## 25. 多轮对话：新用户冷启动

模拟全新用户从 0 开始的完整流程。每条消息在同一 session 中按顺序发送。

| 步骤 | 输入 | 预期输出 | 验证 |
|------|------|---------|------|
| 25.1 | "Hello!" | 产品介绍 | `"introduce_product" in tools_called` |
| 25.2 | "I have a golden retriever named Winnie" | 创建宠物 | `has_card("pet_created")`，`card["species"]=="dog"` |
| 25.3 | "She's 3 years old, weighs 30kg" | 更新信息 | `get_pets()` weight≈30，birthday 大约 3 年前 |
| 25.4 | "She ate chicken and rice today" | 记录事件 | `has_card("record")`，card pet_name 含 "Winnie" |
| 25.5 | "Actually that was yesterday" | 修正日期 | `"update_calendar_event" in tools_called`，date=yesterday |
| 25.6 | "Remind me to take her to the vet next Monday" | 创建提醒 | `has_card("reminder")` |
| 25.7 | "What have I recorded so far?" | 查询事件 | `text` 含 "chicken"/"rice" |
| 25.8 | "She's scared of thunder and very shy" | profile 更新 | `get_pets()` profile_md 含 "thunder"/"shy" |

---

## 26. 多轮对话：一天的完整记录

模拟用户一天中多次与 AI 交互，记录宠物日常。

| 步骤 | 输入 | 预期输出 | 验证 |
|------|------|---------|------|
| 26.1 | "早上给小维喂了狗粮" | record diet | `card["category"]=="diet"` |
| 26.2 | "花了30块买的新狗粮" | 更新刚才那条 cost | `"update_calendar_event" in tools_called`，cost=30 |
| 26.3 | "上午带小维去公园散步了" | record daily | `card["category"]=="daily"` |
| 26.4 | "就是在 Parkdale Park" | 关联地点 | `"add_event_location" in tools_called` |
| 26.5 | 发图片 + "拍了张照片" | 上传到散步事件 | `"upload_event_photo" in tools_called`，event photos 非空 |
| 26.6 | "下午小维吐了" | record abnormal | `card["category"]=="abnormal"` |
| 26.7 | "附近有24小时宠物急诊吗"（带 location） | place_card | `has_card("place_card")` |
| 26.8 | "第一家怎么走？" | directions | `has_card("directions")` |
| 26.9 | "帮我给兽医写一封邮件说明情况" | email | `has_card("email")`，body 含上下文（呕吐、散步等） |
| 26.10 | "今天花了多少钱？" | 查询花费 | `text` 含 "30" |
| 26.11 | "总结一下今天" | 回顾当天事件 | `text` 含 "狗粮"/"公园"/"吐" 等关键信息 |

---

## 27. 多轮对话：上下文引用与指代消歧

测试 LLM 能否正确理解"那个""刚才""上面"等上下文引用。

| 步骤 | 输入 | 预期输出 | 验证 |
|------|------|---------|------|
| 27.1 | "小维今天打了疫苗" | record medical | `has_card("record")` |
| 27.2 | "花了200" | 更新 27.1 的 cost | `"update_calendar_event" in tools_called`，cost=200（不创建新事件） |
| 27.3 | "提醒我下次三个月后再打" | 创建提醒 | `has_card("reminder")`，trigger_at 约 3 个月后 |
| 27.4 | "那条记录标题改成'第二针疫苗'" | 更新 27.1 标题 | `"update_calendar_event" in tools_called` |
| 27.5 | "删掉刚才那个提醒" | 删除 27.3 的提醒 | `has_card("confirm_action")` |
| 27.6 | "再帮我记一条：小维今天洗了澡" | 新的 record | `has_card("record")`，是新事件不是修改 |

---

## 28. 多轮对话：宠物入职全流程

测试从创建宠物到完善档案的多轮流程。

| 步骤 | 输入 | 预期输出 | 验证 |
|------|------|---------|------|
| 28.1 | "我养了一只新猫叫花花" | pet_created | `card["species"]=="cat"` |
| 28.2 | "她是英短蓝猫" | 更新品种 | `get_pets()` breed 含 "英短"/"British" |
| 28.3 | "母的，已经绝育了" | 更新性别+绝育 | gender 非空，neutered=true |
| 28.4 | "体重4公斤，生日2023年6月" | 更新体重+生日 | weight≈4，birthday 含 "2023-06" |
| 28.5 | "对鸡肉过敏" | profile 更新 | profile 含 "过敏"/"allergy" |
| 28.6 | 发图片 + "用这张当头像" | 设置头像 | `"set_pet_avatar" in tools_called`，avatar_url 非空 |
| 28.7 | "帮我总结一下花花的档案" | summarize | `text` 含品种、体重、过敏等全部信息 |
| 28.8 | "花花有什么记录吗" | 查询 | 回复说没有记录（刚创建还没记事件） |

---

## 29. 多轮对话：纠错与撤销链

测试连续纠错场景，验证不会创建重复或搞混。

| 步骤 | 输入 | 预期输出 | 验证 |
|------|------|---------|------|
| 29.1 | "小维今天去体检了" | record medical | `has_card("record")`，event_count=1 |
| 29.2 | "不对，是昨天" | 修改日期 | update，不创建新事件，event_count 仍=1 |
| 29.3 | "分类改成daily" | 修改分类 | update，category=daily |
| 29.4 | "标题改成'年度体检'" | 修改标题 | update，title 含 "体检" |
| 29.5 | "算了，删掉这条" | 删除 | confirm_action 卡片 |
| 29.6 | 确认删除 | 事件消失 | event_count=0 |
| 29.7 | "重新记一下：小维昨天做了年度体检，花了500" | 新事件 | record 卡片，cost=500，date=yesterday |

---

## 30. 多轮对话：混合意图切换

测试在不同功能间快速切换，LLM 不会搞混上下文。

| 步骤 | 输入 | 预期输出 | 验证 |
|------|------|---------|------|
| 30.1 | "小维今天吃了狗粮" | record diet | `has_card("record")` |
| 30.2 | "小维最近拉肚子怎么办？" | search_knowledge | `"search_knowledge" in tools_called`（不是创建 record） |
| 30.3 | "附近有宠物医院吗"（带 location） | search_places | `has_card("place_card")`（不是 search_knowledge） |
| 30.4 | "提醒我明天去那家医院" | create_reminder | `has_card("reminder")`（不是 search_places） |
| 30.5 | "每天提醒我给小维吃益生菌" | create_daily_task | `has_card("daily_task_created")`（不是 create_reminder） |
| 30.6 | "小维突然抽搐了！" | trigger_emergency | `result.emergency` 非空（立即切换，忽略之前上下文） |
| 30.7 | "没事了，虚惊一场" | 普通回复 | `result.emergency` 为空，无工具调用 |

---

## 31. 多轮对话：地点探索完整流程

从搜索到详情到导航到记录的完整地点交互。

| 步骤 | 输入 | 预期输出 | 验证 |
|------|------|---------|------|
| 31.1 | "帮我找附近的狗公园"（带 location） | place_card | `has_card("place_card")` |
| 31.2 | "第一家评价怎么样？" | place_detail | `has_card("place_detail")` |
| 31.3 | "怎么去那里？" | directions | `has_card("directions")` |
| 31.4 | "好，记录一下小维今天去了这个公园" | record + 关联地点 | `has_card("record")`，event location 非空 |

---

## 32. 多轮对话：图片多轮交互

测试图片在多轮对话中的各种场景。

| 步骤 | 输入 | 预期输出 | 验证 |
|------|------|---------|------|
| 32.1 | 发图片 + "小维今天出去玩了" | record + 图片附加 | `has_card("record")`，event photos 非空 |
| 32.2 | "这张照片是什么品种？" （无图，引用上轮） | vision 分析上轮图片 | `"request_images" in tools_called`，`text` 非空 |
| 32.3 | "用刚才那张照片当小维头像" | 设置头像 | `"set_pet_avatar" in tools_called`，avatar_url 非空 |
| 32.4 | 发新图片 + "把这张也加到刚才的记录" | upload_event_photo | `"upload_event_photo" in tools_called`，event photos 长度增加 |
| 32.5 | "删掉第一张照片" | remove_event_photo | `"remove_event_photo" in tools_called` |

---

## 33. 多轮对话：双宠物日常

测试多宠物场景下的上下文消歧和交叉记录。

| 步骤 | 输入 | 预期输出 | 验证 |
|------|------|---------|------|
| 33.1 | "小维今天吃了狗粮" | record，关联小维 | card pet_name 含 "小维"，不含 "花花" |
| 33.2 | "花花也吃了猫粮" | record，关联花花 | card pet_name 含 "花花"，不含 "小维" |
| 33.3 | "它们俩一起去公园玩了" | record，关联两只 | card pet_name 含两只名字 |
| 33.4 | "小维在公园吐了" | record abnormal，只关联小维 | `card["category"]=="abnormal"`，pet_name 仅 "小维" |
| 33.5 | "花花最近吃了什么？" | 查询花花的饮食 | `text` 含 "猫粮"，不含 "狗粮" |
| 33.6 | "提醒我明天给小维喂药" | 创建提醒，关联小维 | 提醒关联 pet 为小维 |
| 33.7 | "花花也要喂" | 创建提醒，关联花花 | 新提醒，关联花花（不修改小维的） |

---

## 34. 多轮对话：待办生命周期

测试待办从创建到完成到删除的完整生命周期。

| 步骤 | 输入 | 预期输出 | 验证 |
|------|------|---------|------|
| 34.1 | "每天提醒我遛狗" | task_created routine | `card["task_type"]=="routine"` |
| 34.2 | "再加一个：每天喂两次药" | task_created | `card["daily_target"]==2` |
| 34.3 | "这周每天给小维量体温" | task_created special | `card["task_type"]=="special"`，有 end_date |
| 34.4 | "我有哪些待办？" | 列出 3 个待办 | `"list_daily_tasks" in tools_called`，`text` 含 "遛狗"/"药"/"体温" |
| 34.5 | "把喂药改成每天3次" | 更新 | daily_target 更新为 3 |
| 34.6 | "取消量体温的任务" | confirm_action | `has_card("confirm_action")` |
| 34.7 | 确认删除 | 待办减少 | list_daily_tasks 返回 2 个 |
| 34.8 | "删除所有待办" | confirm_action | `has_card("confirm_action")` |
| 34.9 | 确认删除 | 全部清空 | list_daily_tasks 返回 0 |

---

## 35. 多轮对话：紧急情况处理全流程

测试从紧急发现到处理到后续记录的完整流程。

| 步骤 | 输入 | 预期输出 | 验证 |
|------|------|---------|------|
| 35.1 | "小维突然开始抽搐了！！" | emergency 事件 | `result.emergency` 非空 |
| 35.2 | "附近有24小时急诊吗"（带 location） | place_card | `has_card("place_card")` |
| 35.3 | "怎么去最近的那家？" | directions | `has_card("directions")` |
| 35.4 | "帮我记录一下，小维今天抽搐发作了" | record abnormal | `card["category"]=="abnormal"` |
| 35.5 | "帮我写封邮件给兽医说明情况" | email | `has_card("email")`，body 含 "抽搐"/"seizure" |
| 35.6 | "提醒我明天带小维复查" | reminder | `has_card("reminder")` |

---

## 36. 多轮对话：语言切换后操作

测试切换语言后工具调用和卡片是否正确。

| 步骤 | 输入 | 预期输出 | 验证 |
|------|------|---------|------|
| 36.1 | "switch to English" | set_language | `"set_language" in tools_called` |
| 36.2 | "Winnie ate dog food today" | record card | `has_card("record")`，card 字段正确 |
| 36.3 | "Delete that record" | confirm_action（英文描述） | confirm card 描述不含 CJK |
| 36.4 | "切换成中文" | set_language(zh) | `"set_language" in tools_called` |
| 36.5 | "小维今天散步了" | record card | `has_card("record")` |
| 36.6 | "删掉这条" | confirm_action（中文描述） | confirm card 描述含 CJK |

---

## 37. 多轮对话：信息逐步补充

测试 LLM 能将多轮补充的信息合并到同一条记录。

| 步骤 | 输入 | 预期输出 | 验证 |
|------|------|---------|------|
| 37.1 | "小维今天去看病了" | record medical | `has_card("record")` |
| 37.2 | "在 Vanier Animal Hospital" | 关联地点 | `"add_event_location" in tools_called` |
| 37.3 | "花了1500" | 更新 cost | event cost=1500 |
| 37.4 | 发图片 + "这是检查报告" | 上传照片 | event photos 非空 |
| 37.5 | "医生说要每天喂益生菌，连续一周" | 创建 special 待办 | `card["task_type"]=="special"`，end_date 约一周后 |
| 37.6 | "提醒我下周复查" | 创建提醒 | `has_card("reminder")` |
| 37.7 | "总结一下这次看病的情况" | 回顾信息 | `text` 含地点、花费、照片、益生菌、复查等 |

---

## 38. 边界场景：工具误用防御

测试 LLM 不该调工具时不调，该调时不调错。

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 38.1 | — | "今天天气真好" | 纯聊天，无工具 | 无 card，无 tools_called |
| 38.2 | — | "你觉得金毛好还是拉布拉多好？" | 纯聊天回答 | 无 `create_pet`，无 `search_knowledge` |
| 38.3 | 有小维 | "小维真可爱" | 纯聊天 | 无 `create_calendar_event`（不是在记录事件） |
| 38.4 | — | "帮我查一下我的宠物" | 调 list_pets | `"list_pets" in tools_called`（不是 query_calendar_events） |
| 38.5 | — | "我的待办" | 调 list_daily_tasks | `"list_daily_tasks" in tools_called`（不是 manage_daily_task） |
| 38.6 | 有事件 | "这条记录不对" | 追问哪里不对 | 不直接删除（需要确认具体修改内容） |
| 38.7 | — | "小维上次中毒是什么时候？" | query 查询 | `result.emergency` 为空，`"query_calendar_events" in tools_called` |
| 38.8 | 有小维 | "我养了一只新狗叫小维" | 不创建重复 | `"create_pet" not in tools_called` |

---

## 39. 多轮对话：长对话上下文保持

测试 10+ 轮后 LLM 仍记得早期信息（通过 context_summary）。

| 步骤 | 输入 | 预期输出 | 验证 |
|------|------|---------|------|
| 39.1 | "小维今天吃了狗粮" | record | `has_card("record")` |
| 39.2 | "下午散步了" | record | `has_card("record")` |
| 39.3 | "晚上洗了澡" | record | `has_card("record")` |
| 39.4 | "小维体重30公斤" | update pet | pet weight=30 |
| 39.5 | "花了50块买了新项圈" | record + cost | `has_card("record")` |
| 39.6 | "提醒我下周打疫苗" | reminder | `has_card("reminder")` |
| 39.7 | "每天遛狗两次" | daily_task | `has_card("daily_task_created")` |
| 39.8 | "小维对鸡肉过敏" | profile update | profile 含 "鸡肉" |
| 39.9 | "附近有狗公园吗"（带 location） | place_card | `has_card("place_card")` |
| 39.10 | "今天总共记了什么？" | 回顾全天 | `text` 含 "狗粮"/"散步"/"洗澡"/"项圈" |
| 39.11 | "小维体重多少来着？" | 回忆之前信息 | `text` 含 "30" |
| 39.12 | "第一条记录是什么？" | 回忆最早的事件 | `text` 含 "狗粮"/"food" |

---

## 40. 复杂指令：一句话多任务

测试用户一句话包含多个不同类型操作时，LLM 能否用 plan 拆分并全部执行。

### 40a. 双任务组合

| # | 输入 | 预期工具 | 验证 |
|---|------|---------|------|
| 40.1 | "记录小维今天吃了狗粮，提醒我明天打疫苗" | create_calendar_event + create_reminder | `has_card("record")` 且 `has_card("reminder")` |
| 40.2 | "小维今天散步了还洗了澡" | 2x create_calendar_event | `card_count("record") >= 2` |
| 40.3 | "帮我删掉昨天的记录，再记一条今天散步了" | delete_calendar_event + create_calendar_event | `has_card("confirm_action")` 且 `has_card("record")` |
| 40.4 | "给小维创建一个每天遛狗的待办，顺便记录今天已经遛了" | create_daily_task + create_calendar_event | `has_card("daily_task_created")` 且 `has_card("record")` |
| 40.5 | "小维体重30公斤，生日2023年3月" | update_pet_profile (weight + birthday) | weight≈30，birthday 含 "2023-03" |

### 40b. 三任务及以上

| # | 输入 | 预期工具 | 验证 |
|---|------|---------|------|
| 40.6 | "今天遛了狗、喂了猫粮、给花花洗了澡"（2只宠物） | 3x create_calendar_event | `card_count("record") >= 3`，宠物关联各不相同 |
| 40.7 | "记录今天散步、提醒明天打疫苗、创建每天喂药的待办" | create_calendar_event + create_reminder + create_daily_task | 3种卡片都有 |
| 40.8 | "小维今天吃了狗粮、下午散步了、晚上洗了澡" | 3x create_calendar_event | `card_count("record") >= 3`，全部关联小维 |

### 40c. 复合操作（一个动作需要多个工具配合）

| # | 输入 | 预期工具 | 验证 |
|---|------|---------|------|
| 40.9 | "带小维去了 Vanier Animal Hospital 做体检" | create_calendar_event + add_event_location | record 卡片 + event 有 location |
| 40.10 | 发图片 + "小维今天去公园玩了，记录一下" | create_calendar_event（图片自动附加） | record 卡片 + event photos 非空 |
| 40.11 | "带小维去医院花了2000，提醒我下周复查" | create_calendar_event(cost=2000) + 提醒 | record cost=2000 + reminder 卡片 |
| 40.12 | "小维和花花今天一起去公园散步了，路上买了零食花了50" | plan → 2x create_calendar_event | 散步关联两只宠物，零食 cost=50 |

### 40d. Plan Nag 验证（确保所有步骤都执行）

| # | 输入 | 预期行为 | 验证 |
|---|------|---------|------|
| 40.13 | "遛了狗、喂了猫粮、洗了澡、打了疫苗" | plan 4步 → 全部执行 | `card_count("record") >= 4`（Plan Nag 确保不遗漏） |
| 40.14 | "记录吃狗粮，记录散步，提醒打疫苗，创建喂药待办" | 4个不同工具 | record ×2 + reminder + daily_task 卡片全有 |

### 40e. 歧义复合指令

| # | 输入 | 预期行为 | 验证 |
|---|------|---------|------|
| 40.15 | "记录一下今天，提醒明天也记" | 记录今天（但记什么？）+ 提醒 | 追问"今天记什么"或合理推断 |
| 40.16 | "删除所有东西" | 追问删什么（不能一次全删） | 不能同时删宠物+事件+待办+提醒 |
| 40.17 | "记录散步"（有2只宠物不指定） | 追问哪只 | 回复含 `?` 或列出宠物选择 |

---

## 41. 多宠物深度场景

### 41a. 3+ 只宠物管理

测试 fixture: 预创建 3 只宠物（小维=dog, 花花=cat, 豆豆=dog）。

| # | 输入 | 预期输出 | 验证 |
|---|------|---------|------|
| 41.1 | "我有几只宠物？" | 列出 3 只 | `text` 含 "小维"/"花花"/"豆豆"，`"list_pets" in tools_called` |
| 41.2 | "小维吃了狗粮" | 只关联小维 | record card pet_name 仅 "小维" |
| 41.3 | "花花也吃了猫粮" | 只关联花花 | record card pet_name 仅 "花花" |
| 41.4 | "豆豆吐了" | 只关联豆豆 | record card pet_name 仅 "豆豆"，category=abnormal |
| 41.5 | "两只狗一起散步了" | 关联小维+豆豆，不含花花 | record pet_name 含 "小维"+"豆豆"，不含 "花花" |
| 41.6 | "所有宠物都打了疫苗" | 3 条 record 或 1 条关联全部 | `card_count("record") >= 1`，所有宠物都被关联 |
| 41.7 | "猫吃了什么？" | 查询花花的饮食 | `text` 含 "猫粮"，不含 "狗粮" |
| 41.8 | "吃了狗粮"（不指定哪只） | 追问哪只狗（有 2 只狗） | 回复含 `?` |

### 41b. 跨宠物操作不混淆

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 41.9 | "小维今天吃了狗粮" | "删掉花花的记录" | 无花花记录可删 | 不删小维的记录 |
| 41.10 | "小维体重30kg" | "花花体重4公斤" | 两只宠物独立更新 | 小维 weight=30，花花 weight=4 |
| 41.11 | "提醒我明天给小维喂药" | "花花也要喂" | 2 个独立提醒 | 各关联正确的宠物 |
| 41.12 | "每天给小维遛狗" | "花花不用" | 只创建小维的待办 | 待办关联小维，花花无待办 |

### 41c. 宠物删除后的隔离

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 41.13 | 有小维+花花，删除花花 | "花花今天吃了猫粮" | 提示花花不存在或自动创建 | 不关联到小维 |
| 41.14 | 有小维+花花，为两只各记事件 | 删除花花后查 "我的记录" | 只显示小维的记录 | `text` 不含花花的事件 |

### 41d. 新宠物加入

| # | setup | 输入 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 41.15 | 有小维 | "我又养了一只猫叫花花" | pet_created | `get_pets()` 数量增加 |
| 41.16 | 41.15 后 | "小维和花花一起去公园了" | record 关联两只 | 新宠物立即可关联 |
| 41.17 | 41.15 后 | "花花3岁了，英短蓝猫" | 更新新宠物 | 花花 breed 和 birthday 更新 |

---

## 42. 宠物共享（双账号 co-owner）

测试两个用户共同照顾同一只宠物的全流程。需要 2 个 E2E client（A=owner, B=co-owner）。

### 42a. 共享建立流程

| # | 操作者 | 操作 | 预期输出 | 验证 |
|---|--------|------|---------|------|
| 42.1 | A | 创建宠物 "小维" | pet_created | A 的 `get_pets()` 含 "小维" |
| 42.2 | A | `POST /pets/{pet_id}/share-token` | 返回 token + expires_at | token 非空，expires 约 10 分钟后 |
| 42.3 | B | `POST /pets/accept-share` with token | 共享成功 | B 的 `get_pets()` 也含 "小维" |
| 42.4 | A | `get_pets()` | 小维仍在 | pet 数据不变 |

### 42b. 共享后数据可见性

| # | 操作者 | 操作 | 预期输出 | 验证 |
|---|--------|------|---------|------|
| 42.5 | A | 聊天 "小维今天吃了狗粮" | record 卡片 | `has_card("record")` |
| 42.6 | B | `get_events(today)` | 能看到 A 创建的事件 | events 列表非空，含 "狗粮" |
| 42.7 | B | 聊天 "小维下午散步了" | record 卡片 | `has_card("record")` |
| 42.8 | A | `get_events(today)` | 能看到 B 创建的事件 | events 含 "散步" |
| 42.9 | A | 聊天 "小维最近怎么样？" | 回复包含两人的记录 | `text` 含 "狗粮" + "散步" |
| 42.10 | B | 聊天 "小维最近吃了什么？" | 能看到 A 的饮食记录 | `text` 含 "狗粮" |

### 42c. 共享宠物的提醒和待办

| # | 操作者 | 操作 | 预期输出 | 验证 |
|---|--------|------|---------|------|
| 42.11 | A | "提醒我明天给小维打疫苗" | reminder 卡片 | `has_card("reminder")` |
| 42.12 | B | "我有什么提醒？" | 能看到 A 创建的提醒 | `text` 含 "疫苗" |
| 42.13 | B | "每天给小维遛狗" | daily_task_created | `has_card("daily_task_created")` |
| 42.14 | A | "我有什么待办？" | 能看到 B 创建的待办 | `text` 含 "遛狗" |

### 42d. created_by 追踪

| # | 操作者 | 操作 | 预期输出 | 验证 |
|---|--------|------|---------|------|
| 42.15 | A 创建事件 | `get_events()` 检查 created_by | 事件 created_by = A 的 user_id | `event["created_by"] == A.user_id` |
| 42.16 | B 创建事件 | `get_events()` 检查 created_by | 事件 created_by = B 的 user_id | `event["created_by"] == B.user_id` |

### 42e. 共享 token 边界

| # | 操作者 | 操作 | 预期输出 | 验证 |
|---|--------|------|---------|------|
| 42.17 | A | 生成 token，等 11 分钟 | token 过期 | B accept-share 返回 410 |
| 42.18 | A | 用同一 token 再次 accept | 已使用 | 返回 404（used=True） |
| 42.19 | A | 自己 accept 自己的 token | 拒绝 | 返回 400 "Cannot share with yourself" |
| 42.20 | B | 已共享，再次 accept 同只宠物 | 拒绝重复 | 返回 400 "Already sharing" |

### 42f. 退出共享

| # | 操作者 | 操作 | 预期输出 | 验证 |
|---|--------|------|---------|------|
| 42.21 | B | `POST /pets/{pet_id}/unshare` keep_copy=false | 退出成功 | B 的 `get_pets()` 不含 "小维" |
| 42.22 | A | `get_pets()` | 小维仍在 | A 不受影响 |
| 42.23 | A | `get_events()` | B 的事件仍在 | 事件不因 B 退出而消失 |

### 42g. 退出并保留副本

| # | 操作者 | 操作 | 预期输出 | 验证 |
|---|--------|------|---------|------|
| 42.24 | B | `POST /pets/{pet_id}/unshare` keep_copy=true | 退出 + 深拷贝 | B 的 `get_pets()` 有一只新 "小维" |
| 42.25 | B | 检查副本 | 宠物信息一致 | 名字/品种/档案与原版一致 |
| 42.26 | B | `get_events()` 检查副本事件 | 事件也被复制 | B 名下有事件副本 |
| 42.27 | A | 修改原版小维信息 | 不影响 B 的副本 | B 的副本 profile 不变 |

### 42h. 合并宠物（merge）

| # | setup | 操作 | 预期输出 | 验证 |
|---|-------|------|---------|------|
| 42.28 | B 已有 "维尼"（同一只的本地版本） | accept-share with merge_pet_id="维尼" | 合并成功 | B 的 "维尼" 被删除，事件迁移到共享的 "小维" |
| 42.29 | 42.28 后 | A 查看事件 | 能看到原属于 "维尼" 的事件 | 事件 pet_id 已更新为共享 pet_id |
| 42.30 | 42.28 后 | B 查看宠物列表 | 只有共享的 "小维" | `get_pets()` 不含 "维尼" |

### 42i. 共享后的对话隔离

| # | 操作者 | 操作 | 预期输出 | 验证 |
|---|--------|------|---------|------|
| 42.31 | A | 发消息 "小维真可爱" | 正常回复 | B 的聊天不会出现这条 |
| 42.32 | B | 发消息 "小维吃了什么？" | 回复含 A 的饮食记录 | 数据共享，聊天独立 |

---

## 43. Duo 订阅与家庭关系

测试 Duo 订阅绑定的家庭关系。

### 43a. 邀请流程

| # | 操作者 | 操作 | 预期输出 | 验证 |
|---|--------|------|---------|------|
| 43.1 | A（Duo 订阅） | `POST /family/invite` email=B | 邀请创建 | `GET /family/status` 有 pending invite |
| 43.2 | B | `POST /family/accept` | 接受成功 | B 的 subscription_status=active |
| 43.3 | A | `GET /family/status` | 显示 member 信息 | role=payer，member 信息存在 |
| 43.4 | B | `GET /family/status` | 显示 payer 信息 | role=member |

### 43b. Duo 降级自动踢出

| # | 操作者 | 操作 | 预期输出 | 验证 |
|---|--------|------|---------|------|
| 43.5 | A | 订阅从 Duo 降级到 Individual | B 被自动踢出 | B 的 subscription_status=expired，family_role=null |
| 43.6 | A | `GET /family/status` | 无 member | role=null |

### 43c. 权限控制

| # | 操作者 | 操作 | 预期输出 | 验证 |
|---|--------|------|---------|------|
| 43.7 | A（Individual 订阅） | `POST /family/invite` | 拒绝 | 需要 Duo 订阅 |
| 43.8 | A（已有 member） | 再邀请 C | 拒绝 | Duo 最多 1 个 member |

### 43d. 撤销伴侣

| # | 操作者 | 操作 | 预期输出 | 验证 |
|---|--------|------|---------|------|
| 43.9 | A | `POST /family/revoke` | member 被撤销 | B 的 family_role=null，subscription 过期 |
| 43.10 | B | 尝试聊天 | 被订阅门控拦截 | 返回 403（subscription expired） |

---

## 工具覆盖检查表（33 个工具）

| 工具 | 测试节 | 用例 |
|------|--------|------|
| `create_calendar_event` | 2 | 2.1-2.19 |
| `query_calendar_events` | 3 | 3.1-3.4 |
| `update_calendar_event` | 4, 24 | 4.1, 4.4, 4.5, 24.1-24.3 |
| `delete_calendar_event` | 4, 20 | 4.2-4.3, 20.2 |
| `upload_event_photo` | 7 | 7.3-7.4 |
| `remove_event_photo` | 7 | 7.9 |
| `add_event_location` | 10 | 10.7-10.8 |
| `create_pet` | 5 | 5.1-5.2 |
| `update_pet_profile` | 5 | 5.3-5.8 |
| `delete_pet` | 5, 20 | 5.10, 20.1 |
| `list_pets` | 5 | 5.11 |
| `save_pet_profile_md` | 15 | 15.1, 15.3 |
| `summarize_pet_profile` | 15 | 15.2 |
| `set_pet_avatar` | 6 | 6.1-6.2 |
| `create_daily_task` | 8 | 8.1-8.3 |
| `list_daily_tasks` | 8 | 8.4-8.5 |
| `manage_daily_task` | 8 | 8.6-8.8 |
| `create_reminder` | 9 | 9.1-9.2 |
| `list_reminders` | 9 | 9.3 |
| `update_reminder` | 9 | 9.4 |
| `delete_reminder` | 9 | 9.5 |
| `delete_all_reminders` | 9 | 9.6 |
| `search_places` | 10 | 10.1-10.2, 10.6 |
| `search_places_text` | 10 | 10.3 |
| `get_place_details` | 10 | 10.4 |
| `get_directions` | 10 | 10.5 |
| `draft_email` | 11 | 11.1-11.2 |
| `trigger_emergency` | 12 | 12.1-12.4 |
| `set_language` | 13 | 13.1-13.4 |
| `request_images` | 7 | 7.6-7.8 |
| `sync_calendar` | 18 | 18.1 |
| `plan` | 19 | 19.1-19.3 |
| `introduce_product` | 1 | 1.5-1.6 |
| `search_knowledge` | 16 | 16.1-16.5 |

---

## 验证枚举参考

```python
_CATEGORIES = {"daily", "diet", "medical", "abnormal"}
_SPECIES = {"dog", "cat", "other"}
_REMINDER_TYPES = {"medication", "vaccine", "checkup", "feeding", "grooming", "other"}
_TASK_TYPES = {"routine", "special"}
_EMERGENCY_ACTIONS = {"find_er", "call_vet", "first_aid"}
_LANGUAGES = {"zh", "en"}
_DAILY_TASK_ACTIONS = {"update", "delete", "deactivate", "delete_all"}
```

## 测试图片

| 文件 | 内容 | 用途 |
|------|------|------|
| `Photos/resized/IMG_1025.PNG` | App 截图（聊天界面） | 发图测试 |
| `Photos/resized/IMG_1027.PNG` | App 截图（日历界面） | 发图测试 |

> 注意：当前仅有 App 截图。建议添加真实宠物照片到 `tests/e2e/fixtures/` 目录（如 `dog.jpg`, `cat.jpg`），用于更真实的图片测试场景。

## 测试结果汇总模板

| 大类 | 用例数 | ✅ | ❌ | ⚠️ |
|------|--------|---|----|----|
| 1. 基础聊天 | 6 | | | |
| 2. 创建事件 | 19 | | | |
| 3. 查询事件 | 4 | | | |
| 4. 修改/删除事件 | 5 | | | |
| 5. 宠物管理 | 11 | | | |
| 6. 宠物头像 | 2 | | | |
| 7. 照片上传 | 9 | | | |
| 8. 每日待办 | 8 | | | |
| 9. 提醒 | 6 | | | |
| 10. 地点搜索 | 8 | | | |
| 11. 邮件草拟 | 2 | | | |
| 12. 紧急情况 | 6 | | | |
| 13. 语言切换 | 4 | | | |
| 14. 多宠物 | 5 | | | |
| 15. 档案管理 | 3 | | | |
| 16. 健康知识 | 5 | | | |
| 17. 上下文压缩 | 2 | | | |
| 18. 日历同步 | 1 | | | |
| 19. 多步规划 | 3 | | | |
| 20. 确认门控 | 6 | | | |
| 21. 边界场景 | 5 | | | |
| 22. i18n 一致性 | 5 | | | |
| 23. Nudge 机制 | 3 | | | |
| 24. 修正记录 | 3 | | | |
| **单功能小计** | **~131** | | | |
| 25. 冷启动流程 | 8 | | | |
| 26. 一天完整记录 | 11 | | | |
| 27. 上下文引用消歧 | 6 | | | |
| 28. 宠物入职流程 | 8 | | | |
| 29. 纠错与撤销链 | 7 | | | |
| 30. 混合意图切换 | 7 | | | |
| 31. 地点探索流程 | 4 | | | |
| 32. 图片多轮交互 | 5 | | | |
| 33. 双宠物日常 | 7 | | | |
| 34. 待办生命周期 | 9 | | | |
| 35. 紧急处理流程 | 6 | | | |
| 36. 语言切换后操作 | 6 | | | |
| 37. 信息逐步补充 | 7 | | | |
| 38. 工具误用防御 | 8 | | | |
| 39. 长对话上下文保持 | 12 | | | |
| 40. 复杂多任务指令 | 17 | | | |
| 41. 多宠物深度场景 | 17 | | | |
| 42. 宠物共享（co-owner） | 32 | | | |
| 43. Duo 订阅与家庭 | 10 | | | |
| **多轮+复杂+共享小计** | **~187** | | | |
| **总计** | **~318** | | | |
