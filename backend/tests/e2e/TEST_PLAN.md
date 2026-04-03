# CozyPup E2E 测试计划

> 更新日期: 2026-04-03
> 分类变更: `excretion`/`vaccine`/`deworming` 已合并为 `abnormal`/`medical`
> 有效分类 (create_calendar_event): `daily`, `diet`, `medical`, `abnormal`
> ⚠️ 注意: `query_calendar_events` 和 `update_calendar_event` 的 category enum 仍含旧值，需要同步修复
> 工具总数: 27 (基于 `_BASE_TOOL_DEFINITIONS`)

## 运行方式

```bash
# 启动后端
cd backend && uvicorn app.main:app --reload --port 8000

# 运行所有 E2E 测试
pytest tests/e2e/ -v --tb=short

# 运行单个模块
pytest tests/e2e/test_tool_calendar.py -v

# 运行所有单元测试
pytest tests/ --ignore=tests/e2e -v
```

---

## 一、基础聊天 (test_chat_basic)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 1.1 | 发送 "你好" / "Hello" | 正常回复，不调任何工具 | `result.text` 非空, 无 card |
| 1.2 | 发送 "hi" | zh 环境用中文回复 | `has_cjk(result.text)` == True |
| 1.3 | 连续发 3 条闲聊 | 每条都正常回复，保持会话上下文 | 3 个 `result.text` 都非空 |

---

## 二、记录日历事件 (test_tool_calendar 2.x)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 2.1 | "小维今天吃了狗粮" | record 卡片, category=**diet**, date=今天 | `card["category"]=="diet"`, `card["date"]==today` |
| 2.2 | "昨天去公园散步了" | record 卡片, category=**daily**, date=昨天 | `card["category"]=="daily"`, `card["date"]==yesterday` |
| 2.3 | "上周五打了疫苗" | record 卡片, category=**medical** | `card["category"]=="medical"` |
| 2.4 | "上周带小维去了医院" | 追问具体日期（不创建事件） | 无 record 卡片, 回复含 `?` 或 `？` |
| 2.5 | "3月20号做了体检" | record 卡片, category=**medical** | `card["category"]=="medical"` |
| 2.6 | "小维吐了" | record 卡片, category=**abnormal** | `card["category"]=="abnormal"` |
| 2.7 | "今天遛了狗还洗了澡" | ≥2 张 record 卡片 | `card_count("record") >= 2` |
| 2.8 | "小维拉稀了" | record 卡片, category=**abnormal** | `card["category"]=="abnormal"` (原 excretion→abnormal) |
| 2.9 | "今天驱虫了" | record 卡片, category=**medical** | `card["category"]=="medical"` (原 deworming→medical) |
| 2.10 | "小维今天游泳了" | record 卡片, category=**daily** | `card["category"]=="daily"` (新增 pattern) |

---

## 三、查询事件 (test_tool_calendar 3.x)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 3.1 | 先创建疫苗记录，再问"上次打疫苗什么时候" | 回复包含疫苗相关内容 | `result.text` 含 "疫苗"/"vaccin" |
| 3.2 | 先创建记录，再问"这周记录了什么" | 回复非空，列出本周事件 | `result.text` 非空 |
| 3.3 | 先创建饮食记录，再问"最近吃了什么" | 回复包含饮食相关内容 | `result.text` 含 "狗粮"/"food"/"eat" |

---

## 四、修改/删除事件 (test_tool_calendar 4.x)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 4.1 | 先创建事件，再说"日期不对，应该是3月25号" | 日期修改成功 | `get_events("2026-03-25")` 有记录 |
| 4.2 | 请求"删掉昨天的散步记录" | 返回 confirm_action 卡片 | `has_card("confirm_action")` |
| 4.3 | 4.2 后确认删除 | 事件被删除 | `get_events(yesterday)` 数量减少 |

---

## 五、宠物管理 (test_tool_pets 5.x)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 5.1 | "我新养了一只猫，叫花花" | pet_created 卡片, species=cat | `has_card("pet_created")`, `card["species"]=="cat"` |
| 5.2 | "花花是母的" | confirm_action 卡片（性别首次设置需确认） | `has_card("confirm_action")` |
| 5.3 | 先设性别=female，再说"其实是公的" | 拒绝修改（性别已锁定） | 回复包含"锁定"/"locked" |
| 5.4 | "花花体重5公斤" | profile_updated 卡片 | `has_card("profile_updated")` |
| 5.5 | "花花生日是2024年3月5号" | profile_updated 卡片 | pet API 返回 `birthday` 含 "2024-03-05" |
| 5.6 | "花花对鸡肉过敏" | profile 更新，allergy 信息记录 | `get_pets()` profile 含 allergy |
| 5.7 | "把花花名字改成咪咪" | profile_updated 卡片，名字变更 | `get_pets()` 有 name="咪咪" |
| 5.8 | 已有小维，再说"我养了一只新狗叫小维" | 拒绝创建（防重复） | 无 pet_created 卡片 |
| 5.9 | "删掉花花" | confirm_action 卡片 | `has_card("confirm_action")` |
| 5.10 | "我有哪些宠物" | 调用 list_pets，回复列出所有宠物 | `result.text` 含宠物名字 |

---

## 六、宠物头像 (set_pet_avatar)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 6.1 | 发送图片 + "用这张做头像" | avatar_updated 卡片 | `has_card("avatar_updated")`, pet.avatar_url 非空 |
| 6.2 | 发送 >5MB 图片 | 拒绝，返回错误 | 回复含 "5MB" |

---

## 七、每日任务 (test_daily_tasks)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 7.1 | "每天提醒我遛狗" | task_created 卡片, type=routine | `has_card("task_created")`, `card["type"]=="routine"` |
| 7.2 | "这周每天给小维量体温" | task_created, type=special, 有起止日期 | `card["type"]=="special"` |
| 7.3 | "取消遛狗的任务" | task deactivated | manage_daily_task 执行成功 |

---

## 八、提醒 (test_tool_reminders 8.x)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 8.1 | "提醒我明天给小维喂药" | reminder 卡片, type=medication | `has_card("reminder")`, `trigger_at` 含明天日期 |
| 8.2 | "下周二带小维去打疫苗，别忘了" | reminder 卡片, type=vaccine | `has_card("reminder")` |
| 8.3 | "我有什么提醒？" | 调用 list_reminders，列出所有活跃提醒 | `result.text` 非空 |
| 8.4 | "取消明天喂药的提醒" | 调用 delete_reminder，提醒被删除 | `has_card("reminder_deleted")` 或回复确认 |
| 8.5 | "把喂药提醒改到后天下午3点" | 调用 update_reminder，更新 trigger_at | 回复确认修改，提醒时间已更新 |
| 8.6 | "取消所有提醒" | 调用 delete_all_reminders，清空全部 | 回复确认已清空，list_reminders 返回空 |

---

## 九、搜索地点 (test_tool_search 9.x)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 9.1 | "附近有宠物医院吗" (传 location) | map/places 卡片 | `has_card("map")` 或 `has_card("places")` |
| 9.2 | "帮我找最近的狗公园" (传 location) | map/places 卡片 | 同上 |
| 9.3 | search_places_text: "北京宠物医院" | 返回地点列表 | 回复含地址信息 |

---

## 十、草拟邮件 (test_tool_email 10.x)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 10.1 | "帮我写一封邮件给兽医，说明皮肤过敏" | email 卡片，含 subject + body | `has_card("email")` |

---

## 十一、紧急情况 (test_tool_emergency 11.x)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 11.1 | "我的猫突然抽搐了！" | emergency SSE 事件 + 急救建议 | `result.emergency` 非空 |
| 11.2 | "小维中毒了快死了" | emergency SSE 事件 | `result.emergency` 非空 |
| 11.3 | "上次中毒是什么时候" | 不触发 emergency（历史查询） | `result.emergency` 为空 |

---

## 十二、语言切换 (test_tool_language 12.x)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 12.1 | "switch to English" | set_language 卡片, language=en | `has_card("language")` |
| 12.2 | "切换成中文" | set_language 卡片, language=zh | `has_card("language")` |

---

## 十三、多宠物场景 (test_multi_pet 13.x)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 13.1 | 有 2 只宠物时说"吃了狗粮"（不指定名字） | 追问哪只，或创建共享事件 | 回复含 `?`/`？` 或 record 卡片含 pet_ids |
| 13.2 | "小维和花花一起散步了" | 创建包含两只宠物的事件 | record 卡片存在 |
| 13.3 | 只有 1 只宠物时说"吃了狗粮" | 自动关联唯一宠物 | `has_card("record")` |

---

## 十四、档案管理 (test_profile 14.x)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 14.1 | "小维很怕打雷，性格胆小" | 静默调用 save_pet_profile_md，profile_md 更新含性格信息 | `get_pets()` profile_md 含性格信息 |
| 14.2 | "帮我总结一下小维的档案" | 调用 summarize_pet_profile，返回完整档案文档 | `result.text` 含档案内容 |
| 14.3 | 多轮对话提到新信息后检查 profile_md | save_pet_profile_md 被静默调用，文档包含历史+新信息 | pet.profile_md 含所有已知信息 |

---

## 十五、上下文压缩 (test_context 15.x)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 15.1 | 连续发 7 条消息后问"最近怎么样" | 回复引用之前的对话内容 | `result.text` 非空 |

---

## 十六、事件地点标记 (add_event_location)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 16.1 | 创建事件后说"是在中心公园" | 事件添加 location | 事件 API 返回含 location |

---

## 十七、图片请求 (request_images)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 17.1 | 发送图片 + "帮我记录一下" | LLM 分析图片内容后记录事件 | record 卡片或相关操作 |
| 17.2 | 发送图片 + "这是什么品种" | 调用 request_images 查看图片，回复品种信息 | `result.text` 含品种相关内容 |

---

## 十八、事件照片 (upload_event_photo)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 18.1 | 先创建事件，再发送图片 + "把照片加到刚才的记录上" | 调用 upload_event_photo 附加照片 | 事件 API 返回含 photo_url |
| 18.2 | 没有事件时发送图片 + "加到记录上" | 提示没有可关联的事件 | 回复引导用户先创建事件 |

---

## 十九、日历同步 (sync_calendar)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 19.1 | "把事件同步到手机日历" | 调用 sync_calendar，前端弹出同步选项 | `has_card("sync_calendar")` 或相关 SSE 事件 |
| 19.2 | "连接 Apple 日历" | 调用 sync_calendar | 同上 |

---

## 二十、边界场景 (test_edge_cases 20.x)

| # | 操作 | 期待结果 | 验证方式 |
|---|------|---------|---------|
| 20.1 | 没有宠物时聊天 | 正常回复 | `result.text` 非空 |
| 20.2 | 有宠物但没事件时查询 | 正常回复"还没有记录" | `result.text` 非空 |
| 20.4 | "记录吃了狗粮，提醒明天打疫苗" | ≥2 张卡片（record + reminder） | `card_count >= 2` |

---

## 分类变更速查

| 旧分类 | 新分类 | 触发词示例 |
|--------|--------|-----------|
| `excretion` | **`abnormal`** | 拉稀、拉肚子、大便异常、排便异常 |
| `vaccine` | **`medical`** | 打疫苗、接种、vaccin |
| `deworming` | **`medical`** | 驱虫、deworm |
| `diet` | `diet` (不变) | 吃了、喂了、feeding |
| `abnormal` | `abnormal` (不变) | 吐了、呕吐、不舒服 |
| `medical` | `medical` (不变) | 看医生、去医院、体检 |
| `daily` | `daily` (不变) | 遛狗、散步、洗澡、游泳 |

## 验证器枚举值

```python
_CATEGORIES = {"daily", "diet", "medical", "abnormal"}
_SPECIES = {"dog", "cat", "other"}
_REMINDER_TYPES = {"medication", "vaccine", "checkup", "feeding", "grooming", "other"}
_TASK_TYPES = {"routine", "special"}
_EMERGENCY_ACTIONS = {"find_er", "call_vet", "first_aid"}
_LANGUAGES = {"zh", "en"}
_DAILY_TASK_ACTIONS = {"update", "delete", "deactivate", "delete_all"}
```

## 工具覆盖清单 (27 tools from `_BASE_TOOL_DEFINITIONS`)

| 工具名 | 测试章节 | 状态 |
|--------|---------|------|
| `create_calendar_event` | 二 (2.x) | ✅ |
| `query_calendar_events` | 三 (3.x) | ✅ |
| `update_calendar_event` | 四 (4.x) | ✅ |
| `delete_calendar_event` | 四 (4.x) | ✅ |
| `create_pet` | 五 (5.x) | ✅ |
| `update_pet_profile` | 五 (5.x) | ✅ |
| `delete_pet` | 五 (5.x) | ✅ |
| `list_pets` | 五 (5.10) | ✅ |
| `save_pet_profile_md` | 十四 (14.x) | ✅ |
| `summarize_pet_profile` | 十四 (14.2) | ✅ |
| `set_pet_avatar` | 六 (6.x) | ✅ |
| `create_daily_task` | 七 (7.x) | ✅ |
| `manage_daily_task` | 七 (7.3) | ✅ |
| `create_reminder` | 八 (8.x) | ✅ |
| `list_reminders` | 八 (8.3) | ✅ |
| `update_reminder` | 八 (8.5) | ✅ |
| `delete_reminder` | 八 (8.4) | ✅ |
| `delete_all_reminders` | 八 (8.6) | ✅ |
| `search_places` | 九 (9.x) | ✅ |
| `search_places_text` | 九 (9.3) | ✅ |
| `draft_email` | 十 (10.x) | ✅ |
| `trigger_emergency` | 十一 (11.x) | ✅ |
| `set_language` | 十二 (12.x) | ✅ |
| `add_event_location` | 十六 (16.x) | ✅ |
| `request_images` | 十七 (17.x) | ✅ |
| `upload_event_photo` | 十八 (18.x) | ✅ |
| `sync_calendar` | 十九 (19.x) | ✅ |
