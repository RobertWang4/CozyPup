"""Bilingual test messages — Chinese and English pairs for every test case.

Each key maps to a TEST_PLAN.md item number. Values are {"zh": ..., "en": ...}.
For sequence tests (multiple messages), values are lists.
"""

MESSAGES = {
    # ═══ 一、基础聊天 ═══
    "1.1": {"zh": "你好", "en": "Hello"},
    "1.2": {"zh": "hi", "en": "hi"},
    "1.3_seq": {
        "zh": ["你好", "今天天气真好", "你觉得呢"],
        "en": ["Hello", "The weather is great today", "What do you think"],
    },
    "1.5": {"zh": "你能做什么？", "en": "What can you do?"},
    "1.6": {"zh": "how to use this app", "en": "how to use this app"},

    # ═══ 二、记录日历事件 ═══
    # 2a. 基础记录
    "2.1": {"zh": "小维今天吃了狗粮", "en": "Weiwei ate dog food today"},
    "2.2": {"zh": "昨天去公园散步了", "en": "We went to the park for a walk yesterday"},
    "2.3": {"zh": "上周五打了疫苗", "en": "Got vaccinated last Friday"},
    "2.4": {"zh": "上周带小维去了医院", "en": "Took Weiwei to the hospital last week"},
    "2.5": {"zh": "3月20号做了体检", "en": "Had a checkup on March 20th"},
    "2.6": {"zh": "小维吐了", "en": "Weiwei vomited"},
    "2.7": {"zh": "小维拉肚子了", "en": "Weiwei has diarrhea"},
    "2.8": {"zh": "今天做了驱虫", "en": "Dewormed today"},
    "2.9": {"zh": "小维今天游泳了", "en": "Weiwei went swimming today"},

    # 2b. 多事件拆分
    "2.10": {"zh": "今天遛了狗还洗了澡", "en": "Walked the dog and gave a bath today"},
    "2.11": {
        "zh": "记录吃狗粮，提醒打疫苗",
        "en": "Record eating dog food, remind me about vaccination",
    },
    "2.12": {
        "zh": "遛了狗、喂了狗粮、洗了澡",
        "en": "Walked the dog, fed dog food, and gave a bath",
    },

    # 2c. 花费记录
    "2.13": {"zh": "带小维去医院花了300", "en": "Took Weiwei to the hospital, cost 300"},
    "2.14": {"zh": "洗澡花了80块", "en": "Bath cost 80 yuan"},
    "2.15": {"zh": "小维今天吃了狗粮", "en": "Weiwei ate dog food today"},
    "2.16": {"zh": "体检花了1500", "en": "Checkup cost 1500"},
    "2.17": {
        "zh": "遛狗途中买了零食50块",
        "en": "Bought snacks for 50 yuan during the walk",
    },

    # 2d. 提醒时间
    "2.18": {
        "zh": "明天下午3点带小维去打疫苗，提醒我",
        "en": "Take Weiwei for vaccination tomorrow at 3pm, remind me",
    },
    "2.19": {"zh": "下周二体检别忘了", "en": "Don't forget the checkup next Tuesday"},

    # ═══ 三、查询事件 ═══
    "3.1": {"zh": "小维上次打疫苗是什么时候？", "en": "When was Weiwei's last vaccination?"},
    "3.2": {"zh": "这周记录了什么？", "en": "What was recorded this week?"},
    "3.3": {"zh": "小维最近吃了什么？", "en": "What has Weiwei eaten recently?"},
    "3.4": {"zh": "最近花了多少钱？", "en": "How much have I spent recently?"},

    # ═══ 四、修改/删除事件 ═══
    "4.1": {
        "zh": "刚才那条记录日期不对，应该是3月25号",
        "en": "The date on that last record is wrong, it should be March 25th",
    },
    "4.2": {"zh": "删掉昨天的散步记录", "en": "Delete yesterday's walk record"},
    "4.4": {"zh": "把标题改成'公园散步'", "en": "Change the title to 'Park Walk'"},
    "4.5": {"zh": "其实花了800", "en": "Actually it cost 800"},

    # ═══ 五、宠物管理 ═══
    "5.1": {"zh": "我新养了一只猫叫花花", "en": "I just got a new cat named Huahua"},
    "5.2": {"zh": "I just got a new puppy named Buddy", "en": "I just got a new puppy named Buddy"},
    "5.3": {"zh": "花花是母的", "en": "Huahua is female"},
    "5.4": {"zh": "花花其实是公的", "en": "Actually Huahua is male"},
    "5.5": {"zh": "花花体重5公斤", "en": "Huahua weighs 5 kilograms"},
    "5.6": {"zh": "花花生日是2024年3月5号", "en": "Huahua's birthday is March 5th, 2024"},
    "5.7": {"zh": "花花对鸡肉过敏", "en": "Huahua is allergic to chicken"},
    "5.8": {"zh": "把花花名字改成咪咪", "en": "Change Huahua's name to Mimi"},
    "5.9": {"zh": "我养了一只新狗叫小维", "en": "I got a new dog named Weiwei"},
    "5.10": {"zh": "删掉花花", "en": "Delete Huahua"},
    "5.11": {"zh": "我有几只宠物？", "en": "How many pets do I have?"},

    # ═══ 六、宠物头像 ═══
    "6.1": {"zh": "用这个当小维的头像", "en": "Use this as Weiwei's avatar"},
    "6.2": {"zh": "这是小维", "en": "This is Weiwei"},

    # ═══ 七、照片上传 ═══
    # 7a. 当前 turn 发图 + 创建事件
    "7.1": {"zh": "记录一下小维今天", "en": "Record Weiwei's day today"},
    "7.2": {"zh": "记一下", "en": "Record this"},

    # 7b. 追加照片到已有事件
    "7.3": {"zh": "把这张照片加到刚才的记录", "en": "Add this photo to the last record"},
    "7.4": {"zh": "Add this to the event", "en": "Add this to the event"},

    # 7c. 跨 turn 图片回退
    "7.5": {"zh": "记录一下", "en": "Record this"},
    "7.6": {"zh": "刚才那张照片是什么品种？", "en": "What breed is that in the last photo?"},

    # 7d. 图片 vision 分析
    "7.7": {"zh": "这是什么品种？", "en": "What breed is this?"},
    "7.8": {"zh": "看看这只狗有什么问题吗？", "en": "Does this dog have any health issues?"},

    # 7e. 删除事件照片
    "7.9": {"zh": "把那条记录的照片删掉", "en": "Delete the photo from that record"},

    # ═══ 八、每日待办 ═══
    # 8a. 创建待办
    "8.1": {"zh": "每天提醒我遛狗", "en": "Remind me to walk the dog every day"},
    "8.2": {"zh": "这周每天给小维量体温", "en": "Take Weiwei's temperature every day this week"},
    "8.3": {"zh": "每天喂两次药", "en": "Give medicine twice a day"},

    # 8b. 查询待办
    "8.4": {"zh": "我有什么待办？", "en": "What tasks do I have?"},
    "8.5": {"zh": "我有什么待办？", "en": "What tasks do I have?"},

    # 8c. 管理待办
    "8.6": {"zh": "取消遛狗任务", "en": "Cancel the dog walking task"},
    "8.7": {"zh": "删除所有待办", "en": "Delete all daily tasks"},
    "8.8": {"zh": "把遛狗改成每天2次", "en": "Change dog walking to twice a day"},

    # ═══ 九、提醒 ═══
    "9.1": {"zh": "提醒我明天给小维喂药", "en": "Remind me to give Weiwei medicine tomorrow"},
    "9.2": {
        "zh": "下周二带小维去打疫苗别忘了",
        "en": "Don't forget to take Weiwei for vaccination next Tuesday",
    },
    "9.3": {"zh": "我有什么提醒？", "en": "What reminders do I have?"},
    "9.4": {"zh": "改成后天下午3点", "en": "Change it to the day after tomorrow at 3pm"},
    "9.5": {"zh": "取消明天的喂药提醒", "en": "Cancel tomorrow's medicine reminder"},
    "9.6": {"zh": "取消所有提醒", "en": "Cancel all reminders"},

    # ═══ 十、地点搜索 ═══
    "10.1": {"zh": "附近有宠物医院吗", "en": "Are there any pet hospitals nearby?"},
    "10.2": {"zh": "帮我找最近的狗公园", "en": "Help me find the nearest dog park"},
    "10.3": {"zh": "北京朝阳区宠物医院", "en": "Pet hospitals in downtown Ottawa"},
    "10.4": {"zh": "第一家评价怎么样？", "en": "How are the reviews for the first one?"},
    "10.5": {"zh": "怎么去那里？", "en": "How do I get there?"},
    "10.6": {"zh": "Find a vet near me", "en": "Find a vet near me"},

    # 10b. 事件关联地点
    "10.7": {"zh": "就是在 Central Park", "en": "It was at Central Park"},
    "10.8": {
        "zh": "带小维去了 Vanier Animal Hospital 做体检",
        "en": "Took Weiwei to Vanier Animal Hospital for a checkup",
    },

    # ═══ 十一、邮件草拟 ═══
    "11.1": {
        "zh": "帮我写一封邮件给兽医说明小维最近皮肤过敏",
        "en": "Help me write an email to the vet about Weiwei's recent skin allergy",
    },
    "11.2": {
        "zh": "Draft an email to the vet about Weiwei's vaccination history",
        "en": "Draft an email to the vet about Weiwei's vaccination history",
    },

    # ═══ 十二、紧急情况 ═══
    "12.1": {"zh": "我的猫突然抽搐了！", "en": "My cat is suddenly having seizures!"},
    "12.2": {"zh": "小维中毒了快死了", "en": "Weiwei has been poisoned and is dying!"},
    "12.3": {"zh": "小维呼吸困难！", "en": "My dog is having trouble breathing!"},
    "12.4": {"zh": "My dog is having seizures!", "en": "My dog is having seizures!"},
    "12.5": {"zh": "上次中毒是什么时候", "en": "When was the last poisoning incident?"},
    "12.6": {"zh": "小维以前抽搐过吗？", "en": "Has Weiwei had seizures before?"},

    # ═══ 十三、语言切换 ═══
    "13.1": {"zh": "switch to English", "en": "switch to English"},
    "13.2": {"zh": "切换成中文", "en": "切换成中文"},
    "13.3": {"zh": "说英文", "en": "Speak English"},
    "13.4": {"zh": "speak Chinese", "en": "speak Chinese"},

    # ═══ 十四、多宠物场景 ═══
    "14.1": {"zh": "吃了狗粮", "en": "Ate dog food"},
    "14.2": {
        "zh": "小维和花花一起散步了",
        "en": "Weiwei and Huahua went for a walk together",
    },
    "14.3": {"zh": "吃了狗粮", "en": "Ate dog food"},  # single pet context
    "14.4": {"zh": "小维吃了狗粮", "en": "Weiwei ate dog food"},
    "14.5": {"zh": "花花吐了", "en": "Huahua vomited"},

    # ═══ 十五、档案管理 ═══
    "15.1": {
        "zh": "小维很怕打雷，性格胆小",
        "en": "Weiwei is very afraid of thunder, timid personality",
    },
    "15.2": {"zh": "帮我总结一下小维的档案", "en": "Help me summarize Weiwei's profile"},

    # ═══ 十六、健康知识问答 (RAG) ═══
    "16.1": {"zh": "小维呕吐了怎么办", "en": "What should I do if my dog is vomiting?"},
    "16.2": {"zh": "小维最近老是拉肚子", "en": "My dog Weiwei has had diarrhea recently"},
    "16.3": {
        "zh": "My dog has been vomiting, what should I do?",
        "en": "My dog has been vomiting, what should I do?",
    },
    "16.4": {"zh": "帮我记录小维今天吃了狗粮", "en": "Record that Weiwei ate dog food today"},
    "16.5": {
        "zh": "小维皮肤上有红点，什么情况？",
        "en": "Weiwei has red spots on the skin, what's going on?",
    },

    # ═══ 十七、上下文压缩 ═══
    "17.1_seq": {
        "zh": [
            "小维今天吃了狗粮",
            "还喝了很多水",
            "下午去公园散步了",
            "遇到了一只金毛",
            "它们玩了很久",
            "回来之后洗了澡",
            "小维最近怎么样？",
        ],
        "en": [
            "Weiwei ate dog food today",
            "Also drank a lot of water",
            "Went to the park in the afternoon",
            "Met a golden retriever",
            "They played for a long time",
            "Took a bath after coming back",
            "How has Weiwei been recently?",
        ],
    },

    # ═══ 二十、确认门控 ═══
    "20.1": {"zh": "删掉小维", "en": "Delete Weiwei"},
    "20.2": {"zh": "删掉今天的记录", "en": "Delete today's record"},
    "20.3": {"zh": "取消这个提醒", "en": "Cancel this reminder"},
    "20.4": {"zh": "删除遛狗待办", "en": "Delete the dog walking task"},

    # ═══ 二十一、边界场景 ═══
    "21.1": {"zh": "你好呀", "en": "Hey there"},  # no pets
    "21.2": {"zh": "小维最近怎么样？", "en": "How has Weiwei been recently?"},  # no events
    "21.3": {
        "zh": "a" * 500,
        "en": "a" * 500,
    },
    "21.4": {"zh": "", "en": ""},
    "21.5": {"zh": "记录吃狗粮", "en": "Record eating dog food"},  # no pets

    # ═══ 二十二、i18n 语言一致性 ═══
    "22.1": {"zh": "Delete all daily tasks", "en": "Delete all daily tasks"},
    "22.2": {"zh": "Delete it", "en": "Delete it"},
    "22.3": {"zh": "删除所有待办", "en": "删除所有待办"},
    "22.4": {"zh": "删除这个待办", "en": "Delete this task"},
    "22.5": {"zh": "删除这个待办", "en": "删除这个待办"},

    # ═══ 二十三、Nudge 机制 ═══
    "23.1": {"zh": "附近有宠物医院吗", "en": "Are there any pet hospitals nearby?"},
    "23.2": {"zh": "switch to English", "en": "switch to English"},
    "23.3": {"zh": "小维中毒了！", "en": "Weiwei has been poisoned!"},

    # ═══ 二十四、修正记录 ═══
    "24.1": {
        "zh": "日期不对，应该是3月25号",
        "en": "The date is wrong, it should be March 25th",
    },
    "24.2": {
        "zh": "分类应该是 medical 不是 diet",
        "en": "The category should be medical not diet",
    },
    "24.3": {"zh": "改成'公园散步'", "en": "Change it to 'Park Walk'"},

    # ═══ 二十五、多轮对话：新用户冷启动 ═══
    "25_seq": {
        "zh": [
            "你好！",
            "我养了一只金毛叫小维",
            "她3岁了，体重30公斤",
            "她今天吃了鸡肉拌饭",
            "不对，是昨天的事",
            "提醒我下周一带她去看兽医",
            "我到现在记录了什么？",
            "她很怕打雷，性格胆小",
        ],
        "en": [
            "Hello!",
            "I have a golden retriever named Winnie",
            "She's 3 years old, weighs 30kg",
            "She ate chicken and rice today",
            "Actually that was yesterday",
            "Remind me to take her to the vet next Monday",
            "What have I recorded so far?",
            "She's scared of thunder and very shy",
        ],
    },

    # ═══ 二十六、多轮对话：一天的完整记录 ═══
    "26_seq": {
        "zh": [
            "早上给小维喂了狗粮",
            "花了30块买的新狗粮",
            "上午带小维去公园散步了",
            "就是在 Parkdale Park",
            "拍了张照片",
            "下午小维吐了",
            "附近有24小时宠物急诊吗",
            "第一家怎么走？",
            "帮我给兽医写一封邮件说明情况",
            "今天花了多少钱？",
            "总结一下今天",
        ],
        "en": [
            "Fed Weiwei dog food this morning",
            "Spent 30 yuan on new dog food",
            "Took Weiwei to the park for a walk this morning",
            "It was at Parkdale Park",
            "Took a photo",
            "Weiwei vomited in the afternoon",
            "Is there a 24-hour pet ER nearby?",
            "How do I get to the first one?",
            "Help me write an email to the vet explaining the situation",
            "How much did I spend today?",
            "Summarize today",
        ],
    },

    # ═══ 二十七、多轮对话：上下文引用与指代消歧 ═══
    "27_seq": {
        "zh": [
            "小维今天打了疫苗",
            "花了200",
            "提醒我下次三个月后再打",
            "那条记录标题改成'第二针疫苗'",
            "删掉刚才那个提醒",
            "再帮我记一条：小维今天洗了澡",
        ],
        "en": [
            "Weiwei got vaccinated today",
            "It cost 200",
            "Remind me to get another one in three months",
            "Change that record's title to 'Second vaccination'",
            "Delete that reminder I just made",
            "Also record this: Weiwei had a bath today",
        ],
    },

    # ═══ 二十八、多轮对话：宠物入职全流程 ═══
    "28_seq": {
        "zh": [
            "我养了一只新猫叫花花",
            "她是英短蓝猫",
            "母的，已经绝育了",
            "体重4公斤，生日2023年6月",
            "对鸡肉过敏",
            "用这张当头像",
            "帮我总结一下花花的档案",
            "花花有什么记录吗",
        ],
        "en": [
            "I got a new cat named Huahua",
            "She's a British Shorthair blue cat",
            "Female, already spayed",
            "Weighs 4 kg, birthday June 2023",
            "Allergic to chicken",
            "Use this as the avatar",
            "Help me summarize Huahua's profile",
            "Does Huahua have any records?",
        ],
    },

    # ═══ 二十九、多轮对话：纠错与撤销链 ═══
    "29_seq": {
        "zh": [
            "小维今天去体检了",
            "不对，是昨天",
            "分类改成daily",
            "标题改成'年度体检'",
            "算了，删掉这条",
            # Step 29.6 is confirm_action — skipped
            "重新记一下：小维昨天做了年度体检，花了500",
        ],
        "en": [
            "Weiwei went for a checkup today",
            "No, it was yesterday",
            "Change the category to daily",
            "Change the title to 'Annual checkup'",
            "Never mind, delete this record",
            # Step 29.6 is confirm_action — skipped
            "Let me re-record: Weiwei had an annual checkup yesterday, cost 500",
        ],
    },

    # ═══ 三十、多轮对话：混合意图切换 ═══
    "30_seq": {
        "zh": [
            "小维今天吃了狗粮",
            "小维最近拉肚子怎么办？",
            "附近有宠物医院吗",
            "提醒我明天去那家医院",
            "每天提醒我给小维吃益生菌",
            "小维突然抽搐了！",
            "没事了，虚惊一场",
        ],
        "en": [
            "Weiwei ate dog food today",
            "Weiwei has been having diarrhea recently, what should I do?",
            "Are there any pet hospitals nearby?",
            "Remind me to go to that hospital tomorrow",
            "Remind me to give Weiwei probiotics every day",
            "Weiwei is suddenly having seizures!",
            "It's fine, false alarm",
        ],
    },

    # ═══ 三十一、多轮对话：地点探索完整流程 ═══
    "31_seq": {
        "zh": [
            "帮我找附近的狗公园",
            "第一家评价怎么样？",
            "怎么去那里？",
            "好，记录一下小维今天去了这个公园",
        ],
        "en": [
            "Help me find a dog park nearby",
            "How are the reviews for the first one?",
            "How do I get there?",
            "OK, record that Weiwei went to this park today",
        ],
    },

    # ═══ 三十二、多轮对话：图片多轮交互 ═══
    "32_seq": {
        "zh": [
            "小维今天出去玩了",
            "这张照片是什么品种？",
            "用刚才那张照片当小维头像",
            "把这张也加到刚才的记录",
            "删掉第一张照片",
        ],
        "en": [
            "Weiwei went out to play today",
            "What breed is in this photo?",
            "Use that photo as Weiwei's avatar",
            "Add this one to the earlier record too",
            "Delete the first photo",
        ],
    },

    # ═══ 三十三、多轮对话：双宠物日常 ═══
    "33_seq": {
        "zh": [
            "小维今天吃了狗粮",
            "花花也吃了猫粮",
            "它们俩一起去公园玩了",
            "小维在公园吐了",
            "花花最近吃了什么？",
            "提醒我明天给小维喂药",
            "花花也要喂",
        ],
        "en": [
            "Weiwei ate dog food today",
            "Huahua also ate cat food",
            "They both went to the park together",
            "Weiwei vomited at the park",
            "What has Huahua eaten recently?",
            "Remind me to give Weiwei medicine tomorrow",
            "Huahua needs it too",
        ],
    },

    # ═══ 三十四、多轮对话：待办生命周期 ═══
    "34_seq": {
        "zh": [
            "每天提醒我遛狗",
            "再加一个：每天喂两次药",
            "这周每天给小维量体温",
            "我有哪些待办？",
            "把喂药改成每天3次",
            "取消量体温的任务",
            # Step 34.7 is confirm_action — skipped
            "删除所有待办",
            # Step 34.9 is confirm_action — skipped
        ],
        "en": [
            "Remind me to walk the dog every day",
            "Add another: give medicine twice a day",
            "Take Weiwei's temperature every day this week",
            "What tasks do I have?",
            "Change medicine to three times a day",
            "Cancel the temperature task",
            # Step 34.7 is confirm_action — skipped
            "Delete all tasks",
            # Step 34.9 is confirm_action — skipped
        ],
    },

    # ═══ 三十五、多轮对话：紧急情况处理全流程 ═══
    "35_seq": {
        "zh": [
            "小维突然开始抽搐了！！",
            "附近有24小时急诊吗",
            "怎么去最近的那家？",
            "帮我记录一下，小维今天抽搐发作了",
            "帮我写封邮件给兽医说明情况",
            "提醒我明天带小维复查",
        ],
        "en": [
            "Weiwei suddenly started having seizures!!",
            "Is there a 24-hour pet ER nearby?",
            "How do I get to the nearest one?",
            "Record this: Weiwei had a seizure episode today",
            "Help me write an email to the vet about the situation",
            "Remind me to take Weiwei for a follow-up tomorrow",
        ],
    },

    # ═══ 三十六、多轮对话：语言切换后操作 ═══
    "36_seq": {
        "zh": [
            "switch to English",
            "Winnie ate dog food today",
            "Delete that record",
            "切换成中文",
            "小维今天散步了",
            "删掉这条",
        ],
        "en": [
            "switch to English",
            "Winnie ate dog food today",
            "Delete that record",
            "切换成中文",
            "Weiwei went for a walk today",
            "Delete this record",
        ],
    },

    # ═══ 三十七、多轮对话：信息逐步补充 ═══
    "37_seq": {
        "zh": [
            "小维今天去看病了",
            "在 Vanier Animal Hospital",
            "花了1500",
            "这是检查报告",
            "医生说要每天喂益生菌，连续一周",
            "提醒我下周复查",
            "总结一下这次看病的情况",
        ],
        "en": [
            "Weiwei went to the vet today",
            "At Vanier Animal Hospital",
            "It cost 1500",
            "This is the examination report",
            "The doctor said to give probiotics daily for a week",
            "Remind me to follow up next week",
            "Summarize this vet visit",
        ],
    },

    # ═══ 三十八、边界场景：工具误用防御 ═══
    "38.1": {"zh": "今天天气真好", "en": "The weather is really nice today"},
    "38.2": {
        "zh": "你觉得金毛好还是拉布拉多好？",
        "en": "Do you think Golden Retrievers or Labradors are better?",
    },
    "38.3": {"zh": "小维真可爱", "en": "Weiwei is so cute"},
    "38.4": {"zh": "帮我查一下我的宠物", "en": "Look up my pets"},
    "38.5": {"zh": "我的待办", "en": "My tasks"},
    "38.6": {"zh": "这条记录不对", "en": "This record is wrong"},
    "38.7": {
        "zh": "小维上次中毒是什么时候？",
        "en": "When was Weiwei's last poisoning incident?",
    },
    "38.8": {"zh": "我养了一只新狗叫小维", "en": "I got a new dog named Weiwei"},

    # ═══ 三十九、多轮对话：长对话上下文保持 ═══
    "39_seq": {
        "zh": [
            "小维今天吃了狗粮",
            "下午散步了",
            "晚上洗了澡",
            "小维体重30公斤",
            "花了50块买了新项圈",
            "提醒我下周打疫苗",
            "每天遛狗两次",
            "小维对鸡肉过敏",
            "附近有狗公园吗",
            "今天总共记了什么？",
            "小维体重多少来着？",
            "第一条记录是什么？",
        ],
        "en": [
            "Weiwei ate dog food today",
            "Went for a walk in the afternoon",
            "Had a bath in the evening",
            "Weiwei weighs 30 kg",
            "Spent 50 yuan on a new collar",
            "Remind me to get vaccinated next week",
            "Walk the dog twice a day",
            "Weiwei is allergic to chicken",
            "Are there any dog parks nearby?",
            "What did I record in total today?",
            "How much does Weiwei weigh again?",
            "What was the first record?",
        ],
    },

    # ═══ 四十、复杂指令：一句话多任务 ═══
    # 40a. 双任务组合
    "40.1": {
        "zh": "记录小维今天吃了狗粮，提醒我明天打疫苗",
        "en": "Record that Weiwei ate dog food today, remind me about vaccination tomorrow",
    },
    "40.2": {
        "zh": "小维今天散步了还洗了澡",
        "en": "Weiwei went for a walk and had a bath today",
    },
    "40.3": {
        "zh": "帮我删掉昨天的记录，再记一条今天散步了",
        "en": "Delete yesterday's record and add a new one for today's walk",
    },
    "40.4": {
        "zh": "给小维创建一个每天遛狗的待办，顺便记录今天已经遛了",
        "en": "Create a daily dog walking task for Weiwei, and record that I already walked today",
    },
    "40.5": {
        "zh": "小维体重30公斤，生日2023年3月",
        "en": "Weiwei weighs 30 kg, birthday March 2023",
    },

    # 40b. 三任务及以上
    "40.6": {
        "zh": "今天遛了狗、喂了猫粮、给花花洗了澡",
        "en": "Walked the dog, fed cat food, and gave Huahua a bath today",
    },
    "40.7": {
        "zh": "记录今天散步、提醒明天打疫苗、创建每天喂药的待办",
        "en": "Record today's walk, remind me about vaccination tomorrow, create a daily medicine task",
    },
    "40.8": {
        "zh": "小维今天吃了狗粮、下午散步了、晚上洗了澡",
        "en": "Weiwei ate dog food today, walked in the afternoon, and had a bath in the evening",
    },

    # 40c. 复合操作
    "40.9": {
        "zh": "带小维去了 Vanier Animal Hospital 做体检",
        "en": "Took Weiwei to Vanier Animal Hospital for a checkup",
    },
    "40.10": {
        "zh": "小维今天去公园玩了，记录一下",
        "en": "Weiwei went to the park today, record it",
    },
    "40.11": {
        "zh": "带小维去医院花了2000，提醒我下周复查",
        "en": "Took Weiwei to the hospital, cost 2000, remind me to follow up next week",
    },
    "40.12": {
        "zh": "小维和花花今天一起去公园散步了，路上买了零食花了50",
        "en": "Weiwei and Huahua went to the park together today, bought snacks for 50 on the way",
    },

    # 40d. Plan Nag 验证
    "40.13": {
        "zh": "遛了狗、喂了猫粮、洗了澡、打了疫苗",
        "en": "Walked the dog, fed cat food, gave a bath, and got vaccinated",
    },
    "40.14": {
        "zh": "记录吃狗粮，记录散步，提醒打疫苗，创建喂药待办",
        "en": "Record eating dog food, record walking, remind about vaccination, create medicine task",
    },

    # 40e. 歧义复合指令
    "40.15": {
        "zh": "记录一下今天，提醒明天也记",
        "en": "Record today, remind me to record tomorrow too",
    },
    "40.16": {"zh": "删除所有东西", "en": "Delete everything"},
    "40.17": {"zh": "记录散步", "en": "Record a walk"},

    # ═══ 四十一、多宠物深度场景 ═══
    # 41a. 3+ 只宠物管理
    "41.1": {"zh": "我有几只宠物？", "en": "How many pets do I have?"},
    "41.2": {"zh": "小维吃了狗粮", "en": "Weiwei ate dog food"},
    "41.3": {"zh": "花花也吃了猫粮", "en": "Huahua also ate cat food"},
    "41.4": {"zh": "豆豆吐了", "en": "Doudou vomited"},
    "41.5": {"zh": "两只狗一起散步了", "en": "The two dogs went for a walk together"},
    "41.6": {"zh": "所有宠物都打了疫苗", "en": "All pets got vaccinated"},
    "41.7": {"zh": "猫吃了什么？", "en": "What did the cat eat?"},
    "41.8": {"zh": "吃了狗粮", "en": "Ate dog food"},

    # 41b. 跨宠物操作不混淆
    "41.9": {"zh": "删掉花花的记录", "en": "Delete Huahua's record"},
    "41.10": {"zh": "花花体重4公斤", "en": "Huahua weighs 4 kg"},
    "41.11": {"zh": "花花也要喂", "en": "Huahua needs medicine too"},
    "41.12": {"zh": "花花不用", "en": "Not for Huahua"},

    # 41c. 宠物删除后的隔离
    "41.13": {"zh": "花花今天吃了猫粮", "en": "Huahua ate cat food today"},
    "41.14": {"zh": "我的记录", "en": "My records"},

    # 41d. 新宠物加入
    "41.15": {"zh": "我又养了一只猫叫花花", "en": "I got another cat named Huahua"},
    "41.16": {
        "zh": "小维和花花一起去公园了",
        "en": "Weiwei and Huahua went to the park together",
    },
    "41.17": {"zh": "花花3岁了，英短蓝猫", "en": "Huahua is 3 years old, British Shorthair blue cat"},
}
