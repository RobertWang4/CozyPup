---
name: cozypup-tool-dev
description: |
  CozyPup 工具开发规范。创建或修改 backend/app/agents/ 下的工具时必须使用此 skill。
  覆盖工具定义、执行函数、验证器、预处理器、后处理器五层架构。
  当用户要求添加新工具、修改现有工具、修复工具 bug、或提到 "tool"/"工具" 时触发。
---

# CozyPup 工具开发规范

## 为什么需要这个规范

CozyPup 使用 LLM function calling 执行用户操作。LLM 有两个核心问题：
1. **说了不做** — 声称"已记录"但没调工具
2. **做了但错** — 调了工具但参数错误或捏造数据

`create_calendar_event`（记日记）是最稳定的工具，因为它有五层保障。所有工具都必须达到同等标准。

## 五层架构（以 create_calendar_event 为模板）

### 第 1 层：工具定义（tools.py - TOOL_DEFINITIONS）

定义 LLM 可以调用的函数签名。

```python
{
    "type": "function",
    "function": {
        "name": "create_calendar_event",
        "description": (
            "记录宠物的日常事件到日历。\n"
            "当用户说了已经发生或即将发生的事时使用。\n"
            "不要用于: 问题查询 (用 query_calendar_events)。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_id": {"type": "string", "description": "UUID of the pet."},
                "event_date": {"type": "string", "description": "YYYY-MM-DD format."},
                "title": {"type": "string", "description": "2-8字简短摘要"},
                "category": {
                    "type": "string",
                    "enum": ["diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"],
                },
            },
            "required": ["pet_id", "event_date", "title", "category"],
        },
    },
}
```

**规则：**
- `description` 必须说明**何时用**和**何时不用**
- `required` 必须包含所有关键字段 — 减少 LLM 遗漏参数的概率
- 用 `enum` 约束有限值集 — LLM 传错值时验证器会拦截并重试
- 可选字段明确标注 "Optional"

### 第 2 层：执行函数（tools.py - _create_xxx / _update_xxx）

实际执行数据库操作的函数。

```python
async def _create_calendar_event(
    arguments: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    **kwargs,
) -> dict:
    # 1. 提取参数
    pet_id = uuid.UUID(arguments["pet_id"])
    # 2. 所有权检查
    pet = await db.execute(select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id))
    if not pet.scalar_one_or_none():
        return {"success": False, "error": "Pet not found"}
    # 3. 业务逻辑
    event = CalendarEvent(...)
    db.add(event)
    await db.flush()
    # 4. 返回结果 + card
    return {
        "success": True,
        "event_id": str(event.id),
        "card": {"type": "event_created", ...},  # 前端展示
    }
```

**规则：**
- 必须有所有权检查（`user_id` 过滤）
- 返回 `{"success": bool, ...}` 格式
- 成功时返回 `card` 给前端展示
- 失败时返回 `error` 字符串，LLM 会转达给用户
- 不可信的值（锁定字段）必须在代码层拦截，不依赖 LLM 遵守 prompt

**特殊返回值：**
- `needs_confirm: True` — 返回确认卡片，用户确认后才执行（用于不可逆操作）

### 第 3 层：验证器（validation.py）

在执行前验证 LLM 传的参数格式。验证失败时错误会反馈给 LLM 让它重试。

```python
@_register("create_calendar_event")
def _validate_create_calendar_event(args: dict) -> list[str]:
    errors = _check_required(args, ["pet_id", "event_date", "title", "category"])
    errors += _check_uuid(args, "pet_id")
    errors += _check_date(args, "event_date")
    errors += _check_enum(args, "category", _CATEGORIES, "category")
    errors += _check_time(args, "event_time")  # 可选字段也验证格式
    return errors
```

**规则：**
- 每个工具必须有对应的验证器
- 使用 `_check_required` 检查必填字段
- 使用 `_check_uuid` / `_check_date` / `_check_enum` 检查格式
- 没有验证器的工具 = LLM 传什么都能执行 = bug 的温床

**可用的检查函数：**
| 函数 | 用途 |
|------|------|
| `_check_required(args, fields)` | 必填字段 |
| `_check_uuid(args, field)` | UUID 格式 |
| `_check_date(args, field)` | YYYY-MM-DD |
| `_check_time(args, field)` | HH:MM |
| `_check_datetime(args, field)` | ISO 8601 |
| `_check_enum(args, field, valid_set, label)` | 枚举值 |

### 第 4 层：预处理器（pre_processor.py）

在 LLM 调用前，用正则从用户消息中提取意图和参数，注入到 system prompt 中作为提示。

```python
_CALENDAR_PATTERNS = [
    # (regex, category, confidence)
    (re.compile(r"吃了|喂了|喂食|feeding|fed", re.I), "diet", 0.9),
    (re.compile(r"拉了|拉稀|大便|poop", re.I), "excretion", 0.9),
    ...
]
```

在 `pre_process()` 中匹配到模式后，返回 `SuggestedAction`：

```python
SuggestedAction(
    tool_name="create_calendar_event",
    arguments={
        "pet_id": pet_id,
        "event_date": event_date.isoformat(),
        "title": message[:100],
        "category": category,
    },
    confidence=0.9,
    confirm_description=f"为{pet_name}记录 {category}",
)
```

**confidence 级别：**
| 范围 | 行为 |
|------|------|
| >= 0.8 | 注入到 prompt 作为高置信提示；后处理器可兜底执行 |
| 0.5 - 0.8 | 可显示确认卡片 |
| < 0.5 | 不使用 |

**规则：**
- 正则要覆盖中文和英文
- 用 `_resolve_pets()` 解析目标宠物
- 用 `_resolve_date()` 解析日期
- 用 `_VALUE_EXTRACTORS` 提取具体值
- 问题类消息（`_QUESTION_OVERRIDE`）不触发记录类操作

### 第 5 层：后处理器（post_processor.py）

LLM 回复后的兜底检查。如果 LLM 声称执行了操作但没有调用任何工具，后处理器直接执行预处理器的建议。

```python
# chat_agent.py 中的调用逻辑
if not any_tool_called and suggested_actions and response_claims_action(full_response):
    fallback_cards = await execute_suggested_actions(
        suggested_actions, db, user_id, on_card=on_card,
    )
```

**触发条件（全部满足）：**
1. LLM 没有调用任何工具（`not any_tool_called`）
2. 预处理器有建议的操作（`suggested_actions` 非空）
3. LLM 回复中包含"已记录/已更新/已保存"等声称完成的措辞

**执行规则：**
- 只执行 confidence >= 0.8 的操作
- 执行前仍然走验证器
- 失败不会影响 LLM 已输出的回复

## 添加新工具的检查清单

1. [ ] **tools.py** — 添加工具定义到 `TOOL_DEFINITIONS`
2. [ ] **tools.py** — 实现 `_xxx()` 执行函数，注册到 `_TOOL_HANDLERS`
3. [ ] **validation.py** — 添加 `@_register("xxx")` 验证器
4. [ ] **pre_processor.py** — 添加意图匹配模式（如果是常用操作）
5. [ ] **post_processor.py** — 确认 `_CLAIMED_ACTION` 正则覆盖该工具的"已完成"措辞
6. [ ] **prompts.py / prompts_v2.py** — 在系统 prompt 中描述工具用途
7. [ ] **tool_guide.py** — 添加到决策树

## 修改现有工具的检查清单

1. [ ] 修改是否影响必填字段？→ 同步更新验证器
2. [ ] 修改是否涉及不可逆操作？→ 使用 `needs_confirm` 确认卡片
3. [ ] 修改是否涉及锁定字段？→ 在执行函数中用代码拦截，不依赖 prompt
4. [ ] 预处理器能否提取新增字段的值？→ 添加 `_VALUE_EXTRACTORS`
5. [ ] 后处理器的 `_CLAIMED_ACTION` 正则是否覆盖新的完成措辞？

## 文件路径速查

| 文件 | 职责 |
|------|------|
| `backend/app/agents/tools.py` | 工具定义 + 执行函数 |
| `backend/app/agents/validation.py` | 参数验证器 |
| `backend/app/agents/pre_processor.py` | 预处理器（意图提取） |
| `backend/app/agents/post_processor.py` | 后处理器（兜底执行） |
| `backend/app/agents/chat_agent.py` | 主循环（串联五层） |
| `backend/app/agents/prompts.py` | V1 系统 prompt |
| `backend/app/agents/prompts_v2.py` | V2 系统 prompt |
| `backend/app/agents/tool_guide.py` | 工具决策树 |
