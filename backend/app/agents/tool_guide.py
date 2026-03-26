"""Decision tree for tool selection — injected into the system prompt."""

TOOL_DECISION_TREE = """\
## 工具选择指南
- 用户说了一件【已发生的事】→ create_calendar_event
- 用户【问】过去的记录 → query_calendar_events
- 用户要求【未来提醒我】→ create_reminder
- 用户提供【宠物信息】(体重/生日/过敏/品种/性别) → update_pet_profile（注意：性别和物种已锁定时不可修改）
- 用户要【删除】什么 → 对应 delete_* tool
- 用户要【找附近医院/宠物店】→ search_places
- 用户描述【紧急症状】→ trigger_emergency
- 用户要求【总结/更新宠物档案】→ summarize_pet_profile
- 用户只是聊天/问问题 → 不调工具，直接回复

### 【重要】create_pet vs update_pet_profile
- create_pet 仅用于用户明确说"我有了一只新宠物"或"我养了一只新的"等场景
- 如果用户提到的宠物名字已经在上面的宠物列表中，说明这只宠物已经存在。此时必须用 update_pet_profile，绝对不要再次调用 create_pet 创建重复的宠物
- 用户补充已有宠物的信息（性别、体重、生日等）→ update_pet_profile
- 用户纠正已有宠物的信息 → update_pet_profile
"""
