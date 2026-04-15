"""Tool definitions (OpenAI function calling format) for the Chat Agent."""

import copy

_BASE_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": (
                "记录宠物事件（已发生的或未来计划的）。\n"
                "已发生: 吃了/拉了/打了疫苗/遛了/洗澡了 → 记录到日历。\n"
                "未来计划: 下周一打疫苗/明天带去洗澡 → 记录到日历 + 传 reminder_at 开启提醒。\n"
                "对于所有宠物或主人共有的事件 (买狗粮/逛宠物店)，只调用一次且不传 pet_id。\n"
                "不要用于: 用户询问过去的事 (用 query_calendar_events)。\n"
                "不要用于: 紧急症状 (用 trigger_emergency)。\n"
                "title 必须是 2-8 字摘要，不要用原始句子。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of a single pet. Use pet_ids for multi-pet events.",
                    },
                    "pet_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of pet UUIDs this event applies to. Use for multi-pet events "
                            "(e.g. both dogs went for a walk). OMIT for owner-only events. "
                            "If only one pet, you can use pet_id instead."
                        ),
                    },
                    "event_date": {
                        "type": "string",
                        "description": "Date of the event in YYYY-MM-DD format.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Short 2-8 word description. Do NOT include cost/price in title — use cost parameter instead. E.g. '看医生' not '看医生花300'.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["daily", "diet", "medical", "abnormal"],
                        "description": (
                            "Category: daily (walks, baths, grooming, park visits), "
                            "diet (feeding, food changes, medication given orally), "
                            "medical (vet visits, vaccines, deworming, checkups), "
                            "abnormal (vomiting, diarrhea, unusual excretion, injuries, illness signs)."
                        ),
                    },
                    "event_time": {
                        "type": "string",
                        "description": "Optional time in HH:MM format.",
                    },
                    "raw_text": {
                        "type": "string",
                        "description": "Optional original user text that triggered this record.",
                    },
                    "cost": {
                        "type": "number",
                        "description": (
                            "花费金额（可选）。用户提到花了多少钱时传入。\n"
                            "只传数字，不传货币符号。例如用户说'花了200块' → cost=200。\n"
                            "用户没提到金额就不要传。"
                        ),
                    },
                    "reminder_at": {
                        "type": "string",
                        "description": (
                            "提醒时间 (ISO 8601: YYYY-MM-DDTHH:MM:SS)。\n"
                            "用户说'提醒我'/'别忘了'/'下周一八点打疫苗' → 传 reminder_at。\n"
                            "已发生的事不需要提醒，不要传。\n"
                            "未来的事如果用户要求提醒 → event_date 设为事件日期，reminder_at 设为提醒时间。"
                        ),
                    },
                },
                "required": ["event_date", "title", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_calendar_events",
            "description": (
                "查询宠物的历史事件记录。\n"
                "当用户询问过去发生的事情时使用 (上次打疫苗是什么时候？最近吃了什么？)。\n"
                "不要用于: 记录新发生的事 (用 create_calendar_event)。\n"
                "不要用于: 查看提醒 (用 list_reminders)。\n"
                "可按 pet_id、日期范围、category 过滤。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "Optional UUID of the pet to filter by.",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Optional start date in YYYY-MM-DD format.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Optional end date in YYYY-MM-DD format.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"],
                        "description": "Optional category filter.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_calendar_event",
            "description": (
                "修改已有的日历事件。\n"
                "当用户想更正/修改之前记录的事件时使用 (日期写错了/标题要改)。\n"
                "不要用于: 记录新事件 (用 create_calendar_event)。\n"
                "必须先调 query_calendar_events 获取 event_id。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "UUID of the event to update (from query_calendar_events results).",
                    },
                    "event_date": {
                        "type": "string",
                        "description": "New date in YYYY-MM-DD format.",
                    },
                    "event_time": {
                        "type": "string",
                        "description": "New time in HH:MM format.",
                    },
                    "title": {
                        "type": "string",
                        "description": "New title/description.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["diet", "excretion", "abnormal", "vaccine", "deworming", "medical", "daily"],
                        "description": "New category.",
                    },
                    "cost": {
                        "type": "number",
                        "description": "New cost amount.",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_pet",
            "description": (
                "为用户创建新的宠物档案。\n"
                "当用户说有新宠物要添加时使用 (我养了一只猫/我新买了一只狗)。\n"
                "不要用于: 更新已有宠物信息 (用 update_pet_profile)。\n"
                "不要用于: 改名 (用 update_pet_profile 传 name)。\n"
                "至少需要 name 和 species。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The pet's name."},
                    "species": {"type": "string", "enum": ["dog", "cat", "other"], "description": "The type of animal."},
                    "breed": {"type": "string", "description": "Breed, e.g. 'Golden Retriever'. Empty string if unknown."},
                    "birthday": {"type": "string", "description": "Optional birthday in YYYY-MM-DD format."},
                    "weight": {"type": "number", "description": "Optional weight in kg."},
                    "gender": {"type": "string", "enum": ["male", "female", "unknown"], "description": "Optional gender."},
                    "neutered": {"type": "boolean", "description": "Optional neutered/spayed status."},
                    "coat_color": {"type": "string", "description": "Optional coat color."},
                },
                "required": ["name", "species"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_pet_profile",
            "description": (
                "更新宠物档案信息，包括改名。\n"
                "当用户提到宠物的任何属性时使用 (体重/生日/过敏/品种/性别/饮食/性格/兽医等)。\n"
                "改名: 在 info 里传 {\"name\": \"新名字\"}。\n"
                "不要用于: 添加新宠物 (用 create_pet)。\n"
                "不要用于: 记录事件 (用 create_calendar_event)。\n"
                "主动调用以逐步完善宠物画像。info 是灵活的 key-value 对。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet.",
                    },
                    "info": {
                        "type": "object",
                        "description": (
                            "Key-value pairs of pet info to save. Any keys are allowed. "
                            "Examples: {\"gender\": \"male\", \"weight_kg\": 5.2, \"allergies\": [\"chicken\"], "
                            "\"diet\": \"Royal Canin 200g 2x/day\", \"neutered\": true, \"vet\": \"瑞鹏医院\", "
                            "\"temperament\": \"friendly but anxious\", \"coat_color\": \"golden\"}"
                        ),
                    },
                },
                "required": ["pet_id", "info"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_pet_profile_md",
            "description": (
                "保存/更新宠物的叙事性档案文档 (markdown)。\n"
                "当从对话中了解到宠物新信息时静默调用 (性格/病史/日常习惯/偏好)。\n"
                "不要用于: 更新结构化字段如体重/生日 (用 update_pet_profile)。\n"
                "必须传完整文档 (非 diff)，500 字以内，用 markdown 分节。\n"
                "用用户的语言撰写。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet.",
                    },
                    "profile_md": {
                        "type": "string",
                        "description": (
                            "The FULL markdown profile document. Include all previously known info "
                            "plus new info. Sections: basics, personality, health, daily routine."
                        ),
                    },
                },
                "required": ["pet_id", "profile_md"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_pet_profile",
            "description": (
                "用户主动要求总结/更新宠物档案时调用。\n"
                "回顾所有已知信息和聊天历史，生成完整的宠物档案文档。\n"
                "仅在用户明确要求时调用 (帮我总结一下XX的信息/更新一下档案/整理一下宠物资料)。\n"
                "必须传完整文档 (非 diff)，800 字以内，用 markdown 分节。\n"
                "用用户的语言撰写，尽量丰富详实。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet.",
                    },
                    "profile_md": {
                        "type": "string",
                        "description": (
                            "The FULL markdown profile document. Summarize ALL known info about the pet "
                            "from conversation history and existing profile. Sections: basics, personality, "
                            "health, daily routine, notes. Be thorough and detailed."
                        ),
                    },
                },
                "required": ["pet_id", "profile_md"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pets",
            "description": (
                "列出用户所有已注册的宠物及其档案。\n"
                "当用户问自己有哪些宠物、或你需要查 pet_id 时使用。\n"
                "不要用于: 创建新宠物 (用 create_pet)。\n"
                "无参数，返回全部宠物列表。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": (
                "【已弃用 — 请改用 create_calendar_event + reminder_at 参数】\n"
                "如果用户说'提醒我明天喂药'，应调用 create_calendar_event(event_date=明天, title=喂药, category=medical, reminder_at=明天的时间)。\n"
                "仅当 LLM 仍然调用此工具时作为兼容层，内部会自动转为 calendar event。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet this reminder is for.",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["medication", "vaccine", "checkup", "feeding", "grooming", "other"],
                        "description": "Type of reminder.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Short reminder title, e.g. 'Give heartworm medication'.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional detailed description.",
                    },
                    "trigger_at": {
                        "type": "string",
                        "description": "When to send the reminder, in ISO 8601 format (YYYY-MM-DDTHH:MM:SS).",
                    },
                },
                "required": ["pet_id", "type", "title", "trigger_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_places",
            "description": (
                "搜索附近的宠物相关地点 (宠物医院/宠物店/狗公园/美容店/24h急诊)。\n"
                "【必须调用】当用户提到以下任何一种时，必须调用此工具:\n"
                "- '附近''附近哪里有''帮我找''最近的' + 宠物医院/医院/宠物店/狗公园/公园/美容店\n"
                "- 'nearby''find''closest''nearest' + vet/clinic/hospital/dog park/pet store/groomer\n"
                "- 需要找宠物相关地点的任何表达\n"
                "即使没有位置信息也要调用，系统会自动处理。\n"
                "不要用于: 记录去过的地方 (用 create_calendar_event)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search query for Google Places, e.g. 'veterinary clinic', "
                            "'dog park', '24 hour emergency vet'."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_email",
            "description": (
                "生成邮件草稿卡片供用户审阅和发送。\n"
                "当用户要写邮件给兽医或宠物服务商时使用。\n"
                "不要用于: 聊天回复 (直接回复即可)。\n"
                "你来根据对话上下文撰写邮件内容，然后调用此工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "Email subject line.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Full email body text.",
                    },
                },
                "required": ["subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_pet",
            "description": (
                "删除宠物档案。\n"
                "当用户明确要求移除某个宠物时使用。\n"
                "不要用于: 更新宠物信息 (用 update_pet_profile)。\n"
                "此操作不可逆，需确认用户意图。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet to delete.",
                    },
                },
                "required": ["pet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event",
            "description": (
                "删除日历事件记录。\n"
                "当用户要求删除之前记录的事件时使用。\n"
                "不要用于: 修改事件 (用 update_calendar_event)。\n"
                "必须先调 query_calendar_events 获取 event_id。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "UUID of the event to delete (from query_calendar_events results).",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": (
                "列出用户所有未发送的提醒。\n"
                "当用户问有哪些提醒/定时任务时使用。\n"
                "不要用于: 查看历史事件 (用 query_calendar_events)。\n"
                "无参数，返回全部活跃提醒。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_reminder",
            "description": (
                "修改已有的提醒。\n"
                "当用户要改提醒的时间/标题/内容时使用。\n"
                "不要用于: 创建新提醒 (用 create_reminder)。\n"
                "必须先调 list_reminders 获取 reminder_id。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {
                        "type": "string",
                        "description": "UUID of the reminder to update (from list_reminders results).",
                    },
                    "title": {
                        "type": "string",
                        "description": "New reminder title.",
                    },
                    "body": {
                        "type": "string",
                        "description": "New reminder body/description.",
                    },
                    "trigger_at": {
                        "type": "string",
                        "description": "New trigger time in ISO 8601 format (YYYY-MM-DDTHH:MM:SS).",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["medication", "vaccine", "checkup", "feeding", "grooming", "other"],
                        "description": "New reminder type.",
                    },
                },
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_reminder",
            "description": (
                "删除/取消一个提醒。\n"
                "当用户要取消某一个已设定的提醒时使用。\n"
                "不要用于: 修改提醒 (用 update_reminder)。\n"
                "不要用于: 删除全部提醒 (用 delete_all_reminders)。\n"
                "必须先调 list_reminders 获取 reminder_id。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {
                        "type": "string",
                        "description": "UUID of the reminder to delete (from list_reminders results).",
                    },
                },
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_all_reminders",
            "description": (
                "删除用户所有未发送的提醒。\n"
                "当用户要求清空/删除全部提醒时使用。\n"
                "不要用于: 删除单个提醒 (用 delete_reminder)。\n"
                "不需要 reminder_id，直接清空所有待发送提醒。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upload_event_photo",
            "description": (
                "将用户的照片附加到日历事件。\n"
                "【必须调用】当用户发了照片并且：\n"
                "  - 要求关联到某条记录/事件\n"
                "  - 说'加照片''添加图片''附加到...'\n"
                "  - 对话上下文中刚刚创建了事件且用户补发了照片\n"
                "照片自动从用户消息中获取，需要先有 event_id（可通过 query_calendar_events 查找）。\n"
                "不要用于: 设置宠物头像 (用 set_pet_avatar)。\n"
                "⚠️ 不要只调 request_images 看图就结束！看完图后必须调此工具实际附加照片。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "UUID of the event to attach the photo to.",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_event_photo",
            "description": (
                "删除日历事件中的某一张照片。\n"
                "【何时调用】用户说要删掉某张照片时调用。\n"
                "需要 event_id 和 photo_index（从0开始的序号）。\n"
                "先用 query_calendar_events 查到事件，确认照片数量后再调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "UUID of the event.",
                    },
                    "photo_index": {
                        "type": "integer",
                        "description": "0-based index of the photo to remove.",
                    },
                },
                "required": ["event_id", "photo_index"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_language",
            "description": (
                "切换应用界面显示语言。\n"
                "【必须调用】当用户说以下任何一种时，必须调用此工具:\n"
                "- '切换成中文''切换成英文''说中文''说英文''用中文''用英文'\n"
                "- 'switch to English''switch to Chinese''use English''use Chinese''speak English''speak Chinese'\n"
                "- 任何要求改变回复/界面语言的表达\n"
                "调用此工具时同时切换你的回复语言。\n"
                "不要用于: 翻译内容 (直接用目标语言回复)。\n"
                "支持 zh 和 en。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "enum": ["zh", "en"],
                        "description": "Language code to switch to.",
                    },
                },
                "required": ["language"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_pet_avatar",
            "description": (
                "设置宠物头像。\n"
                "当用户发了照片并说要用作宠物头像时使用。\n"
                "如果用户要求用之前发过的照片设置头像，从对话上下文中找到该图片的 photo_url（格式如 /api/v1/calendar/photos/xxx.jpg）传入即可，无需用户重新发送。\n"
                "不要用于: 给事件附加照片 (用 upload_event_photo)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "UUID of the pet.",
                    },
                    "photo_url": {
                        "type": "string",
                        "description": "URL of a previously uploaded photo (e.g. /api/v1/calendar/photos/xxx.jpg). Use when referencing a photo from earlier in the conversation instead of a newly attached image.",
                    },
                },
                "required": ["pet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_emergency",
            "description": (
                "【紧急情况必须调用】当用户描述宠物正在经历危及生命的状况时，必须立即调用。\n"
                "触发场景: 抽搐/seizure、中毒/poisoning、大出血/bleeding、呼吸困难/breathing difficulty、\n"
                "昏迷/unconscious、快死了/dying、口吐白沫、翻白眼、站不起来、被车撞、误食有毒物等。\n"
                "只要用户描述的是【正在发生】或【刚刚发生】的紧急症状，就必须调用此工具。\n"
                "不调用的唯一情况: 用户明确在问【过去的】事件（'上次中毒是什么时候'）或进行一般性讨论。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "给用户的紧急提示消息",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["find_er", "call_vet", "first_aid"],
                        "description": "建议的紧急操作类型",
                    },
                },
                "required": ["message", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_daily_task",
            "description": (
                "创建每日待办任务。\n"
                "当用户想设置每天要做的事情时使用（遛狗、喂食、吃益生菌等）。\n"
                "【end_date 规则】\n"
                "- 用户没提到截止时间 → 不传 end_date（永久重复）\n"
                "- 用户说了截止时间 → 必须传 end_date！\n"
                "  '到下周日' → 算出具体日期，如 2026-04-06\n"
                "  '到4月10号' → end_date='2026-04-10'\n"
                "  '接下来7天' → end_date = 今天 + 7 天\n"
                "  '这周' → end_date = 本周日日期\n"
                "漏传 end_date 是严重错误，等于把限期任务变成了永久任务。\n"
                "不要用于: 一次性提醒 (用 create_reminder)。\n"
                "不要用于: 记录已发生的事 (用 create_calendar_event)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Task title, e.g. '遛狗', '吃益生菌'."},
                    "daily_target": {"type": "integer", "description": "How many times per day (default 1)."},
                    "pet_id": {"type": "string", "description": "Optional UUID of the pet this task is for."},
                    "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD). Default: today."},
                    "end_date": {"type": "string", "description": "End date (YYYY-MM-DD). MUST pass when user mentions any deadline ('到X', 'until X', '接下来N天'). Omit ONLY for permanent tasks."},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_daily_tasks",
            "description": (
                "列出用户所有活跃的每日待办任务。\n"
                "【必须调用】当用户问有什么待办/任务/要做的事时，必须调用此工具获取列表，再基于结果回答。\n"
                "不要用于: 查询提醒 (用 list_reminders)。\n"
                "不要用于: 删除或修改待办 (用 manage_daily_task)。\n"
                "无参数，返回所有活跃待办。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_daily_task",
            "description": (
                "编辑或删除已有的每日待办任务。\n"
                "当用户想修改待办的标题、频次、日期，或删除/暂停待办时使用。\n"
                "可以通过 task_id 精确匹配，或通过 title 关键词模糊匹配。\n"
                "不要用于: 创建新待办 (用 create_daily_task)。\n"
                "不要用于: 查询有什么待办 (用 list_daily_tasks)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["update", "delete", "deactivate", "delete_all"], "description": "update=修改, delete=删除单个, deactivate=暂停, delete_all=删除全部待办(不需要task_id/title)."},
                    "task_id": {"type": "string", "description": "UUID of the task (if known)."},
                    "title": {"type": "string", "description": "Task title keyword for fuzzy matching."},
                    "updates": {
                        "type": "object",
                        "description": "Fields to update: title, daily_target, end_date.",
                        "properties": {
                            "title": {"type": "string"},
                            "daily_target": {"type": "integer"},
                            "end_date": {"type": "string"},
                        },
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_event_location",
            "description": (
                "给日记/日历事件添加地点标记。\n"
                "当用户选择了一个地点后使用。\n"
                "需要先有 event_id（来自 create_calendar_event 的返回值）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "Calendar event UUID.",
                    },
                    "location_name": {
                        "type": "string",
                        "description": "Place name, e.g. 'Rideau Park'.",
                    },
                    "location_address": {
                        "type": "string",
                        "description": "Full address.",
                    },
                    "lat": {
                        "type": "number",
                        "description": "Latitude.",
                    },
                    "lng": {
                        "type": "number",
                        "description": "Longitude.",
                    },
                    "place_id": {
                        "type": "string",
                        "description": "Google Place ID.",
                    },
                },
                "required": ["event_id", "location_name", "lat", "lng"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_places_text",
            "description": (
                "通过文字查询搜索具体地点（地址或地名）。\n"
                "当用户说了一个具体地址时使用，如 '302 Rideau St' 或 '朝阳公园'。\n"
                "返回前5个匹配结果。\n"
                "不要用于: 搜索附近地点（用 search_places）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Address or place name to search for.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_place_details",
            "description": (
                "查询地点的详细信息（评论、营业时间、电话等）。\n"
                "【何时调用】用户问某个地点的评价、服务项目、营业时间、能不能做X时调用。\n"
                "需要 place_id（来自 search_places 的返回值）。\n"
                "不要用于: 搜索地点（用 search_places）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "place_id": {
                        "type": "string",
                        "description": "Google Place ID from search_places result.",
                    },
                },
                "required": ["place_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_directions",
            "description": (
                "获取从用户当前位置到目的地的路线信息。\n"
                "【何时调用】用户说'怎么去''导航''多远''多久能到'时调用。\n"
                "需要目的地坐标（来自 search_places 的返回值）。\n"
                "不要用于: 搜索地点（用 search_places）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dest_lat": {
                        "type": "number",
                        "description": "Destination latitude.",
                    },
                    "dest_lng": {
                        "type": "number",
                        "description": "Destination longitude.",
                    },
                    "dest_name": {
                        "type": "string",
                        "description": "Destination place name (for display).",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["driving", "walking"],
                        "description": "Travel mode. Default: driving.",
                    },
                },
                "required": ["dest_lat", "dest_lng", "dest_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_images",
            "description": (
                "请求查看用户附带的图片。\n"
                "当你需要看图片内容才能回答用户问题时调用（什么颜色/什么品种/图片里是什么）。\n"
                "不要用于: 换头像、存日记等操作（那些工具会自动接收图片，不需要你先看）。\n"
                "调用后图片会返回给你，你再根据图片内容回答用户。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "为什么需要看图片，例如'用户问宠物颜色'",
                    },
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sync_calendar",
            "description": (
                "同步宠物事件到用户的 Apple 日历。\n"
                "当用户要求同步日历、连接日历、或说'把事件同步到手机日历'时使用。\n"
                "当用户在新设备上登录后想恢复日历数据时使用。\n"
                "不需要参数，前端会弹出选项让用户选择同步方式。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan",
            "description": (
                "将复杂请求拆解为多个步骤，然后逐步执行。\n"
                "【必须调用】当用户一句话里包含 ≥2 件不同的事时，必须先调用此工具拆分，再逐个执行。\n"
                "例如: '遛了狗还洗了澡' → 2步, '记录吃狗粮，提醒明天打疫苗' → 2步。\n"
                "不要用于: 单一事件 (直接调对应工具)。\n"
                "每个 step 指定要调用的 tool 名和动作描述。plan 后立即开始执行第一步。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer", "description": "Step number, starting from 1."},
                                "action": {"type": "string", "description": "What this step does, e.g. '记录遛狗 daily'."},
                                "tool": {"type": "string", "description": "Tool name to call, e.g. 'create_calendar_event'."},
                            },
                            "required": ["id", "action", "tool"],
                        },
                        "description": "List of steps to execute in order.",
                    },
                },
                "required": ["steps"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "introduce_product",
            "description": (
                "向用户介绍 Cozy Pup 的功能和使用方式。\n"
                "【必须调用】以下场景必须调用此工具：\n"
                "1. 新用户的第一条消息（系统提示会标注）\n"
                "2. 用户问「你能做什么」「有什么功能」「怎么用」「帮助」「能记录什么」\n"
                "调用此工具时，不要同时调用其他工具（如 create_calendar_event）。\n"
                "用户在问功能，不是在记录事件。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "检索宠物健康知识库和用户历史记录，用于回答健康相关问题。\n"
                "【必须调用】用户描述宠物健康问题、症状、疾病、用药、饮食疑问时。\n"
                "如果用户发了图片（如呕吐物/皮肤/便便），从图片中观察到的症状特征作为 query。\n"
                "不要用于: 闲聊、创建日程、记录事件（用对应工具）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，描述症状或健康问题",
                    },
                    "pet_id": {
                        "type": "string",
                        "description": "相关宠物的 UUID，可选。明确知道是哪只宠物时传入",
                    },
                    "species": {
                        "type": "string",
                        "enum": ["dog", "cat"],
                        "description": "物种，用于过滤知识库",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

# Backward compatibility alias
TOOL_DEFINITIONS = _BASE_TOOL_DEFINITIONS

_tool_defs_cache: dict[str, list[dict]] = {}  # Cleared on module reload


def get_tool_definitions(lang: str = "zh") -> list[dict]:
    """Return tool definitions with localized descriptions (cached per lang)."""
    if lang in _tool_defs_cache:
        return _tool_defs_cache[lang]

    from app.agents.locale import t

    if lang == "zh":
        _tool_defs_cache[lang] = _BASE_TOOL_DEFINITIONS
        return _BASE_TOOL_DEFINITIONS
    tools = copy.deepcopy(_BASE_TOOL_DEFINITIONS)
    for tool in tools:
        fn = tool["function"]
        key = f"tool_desc_{fn['name']}"
        desc = t(key, lang)
        if desc != key:
            fn["description"] = desc
    _tool_defs_cache[lang] = tools
    return tools
