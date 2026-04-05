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

    # ═══ 二、记录日历事件 ═══
    "2.1": {"zh": "小维今天吃了狗粮", "en": "Weiwei ate dog food today"},
    "2.2": {"zh": "昨天去公园散步了", "en": "We went to the park for a walk yesterday"},
    "2.3": {"zh": "上周五打了疫苗", "en": "Got vaccinated last Friday"},
    "2.4": {"zh": "上周带小维去了医院", "en": "Took Weiwei to the hospital last week"},
    "2.5": {"zh": "3月20号做了体检", "en": "Had a checkup on March 20th"},
    "2.6": {"zh": "小维吐了", "en": "Weiwei vomited"},
    "2.7": {"zh": "今天遛了狗还洗了澡", "en": "Walked the dog and gave a bath today"},

    # ═══ 二(补)、分类合并测试 ═══
    "2.8": {"zh": "小维拉稀了", "en": "Weiwei has diarrhea"},
    "2.9": {"zh": "今天驱虫了", "en": "Dewormed today"},
    "2.10": {"zh": "小维今天游泳了", "en": "Weiwei went swimming today"},

    # ═══ 三、查询事件 ═══
    "3.1": {"zh": "小维上次打疫苗是什么时候？", "en": "When was Weiwei's last vaccination?"},
    "3.2": {"zh": "这周记录了什么？", "en": "What was recorded this week?"},
    "3.3": {"zh": "小维最近吃了什么？", "en": "What has Weiwei eaten recently?"},

    # ═══ 四、修改/删除事件 ═══
    "4.1": {
        "zh": "刚才那条记录日期不对，应该是3月25号",
        "en": "The date on that last record is wrong, it should be March 25th",
    },
    "4.2": {"zh": "删掉昨天的散步记录", "en": "Delete yesterday's walk record"},

    # ═══ 五、宠物管理 ═══
    "5.1": {"zh": "我新养了一只猫，叫花花", "en": "I got a new cat named Huahua"},
    "5.2": {"zh": "花花是母的", "en": "Huahua is female"},
    "5.3": {"zh": "花花其实是公的", "en": "Actually Huahua is male"},
    "5.4": {"zh": "花花体重5公斤", "en": "Huahua weighs 5 kilograms"},
    "5.5": {"zh": "花花生日是2024年3月5号", "en": "Huahua's birthday is March 5th, 2024"},
    "5.6": {"zh": "花花对鸡肉过敏", "en": "Huahua is allergic to chicken"},
    "5.7": {"zh": "把花花名字改成咪咪", "en": "Change Huahua's name to Mimi"},
    "5.8": {"zh": "我养了一只新狗叫小维", "en": "I got a new dog named Weiwei"},
    "5.9": {"zh": "删掉花花", "en": "Delete Huahua"},

    # ═══ 八、提醒 ═══
    "8.1": {"zh": "提醒我明天给小维喂药", "en": "Remind me to give Weiwei medicine tomorrow"},
    "8.2": {
        "zh": "下周二带小维去打疫苗，别忘了",
        "en": "Don't forget to take Weiwei for vaccination next Tuesday",
    },
    "8.3": {"zh": "我有什么提醒？", "en": "What reminders do I have?"},
    "8.4": {"zh": "取消明天喂药的提醒", "en": "Cancel tomorrow's medicine reminder"},

    # ═══ 九、搜索地点 ═══
    "9.1": {"zh": "附近有宠物医院吗", "en": "Are there any pet hospitals nearby?"},
    "9.2": {"zh": "帮我找最近的狗公园", "en": "Help me find the nearest dog park"},
    "9.4": {"zh": "第一家评价怎么样？", "en": "How are the reviews for the first one?"},
    "9.5": {"zh": "怎么去那里？", "en": "How do I get there?"},

    # ═══ 十、草拟邮件 ═══
    "10.1": {
        "zh": "帮我写一封邮件给兽医，说明小维最近皮肤过敏",
        "en": "Help me write an email to the vet about Weiwei's recent skin allergy",
    },

    # ═══ 十一、紧急情况 ═══
    "11.1": {"zh": "我的猫突然抽搐了！", "en": "My cat is suddenly having seizures!"},
    "11.2": {"zh": "小维中毒了快死了", "en": "Weiwei has been poisoned and is dying!"},
    "11.3": {"zh": "上次中毒是什么时候", "en": "When was the last poisoning incident?"},

    # ═══ 十二、语言切换 ═══
    "12.1": {"zh": "switch to English", "en": "switch to English"},
    "12.2": {"zh": "切换成中文", "en": "切换成中文"},

    # ═══ 十三、多宠物场景 ═══
    "13.1": {"zh": "吃了狗粮", "en": "Ate dog food"},
    "13.2": {
        "zh": "小维和花花一起散步了",
        "en": "Weiwei and Huahua went for a walk together",
    },
    "13.3": {"zh": "吃了狗粮", "en": "Ate dog food"},  # single pet context

    # ═══ 十四、档案管理 ═══
    "14.1": {
        "zh": "小维很怕打雷，性格胆小",
        "en": "Weiwei is very afraid of thunder, timid personality",
    },
    "14.2": {"zh": "帮我总结一下小维的档案", "en": "Help me summarize Weiwei's profile"},

    # ═══ 十五、上下文压缩 ═══
    "15.1_seq": {
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

    # ═══ 二十、边界场景 ═══
    "20.1": {"zh": "你好呀", "en": "Hey there"},  # no pets
    "20.2": {"zh": "小维最近怎么样？", "en": "How has Weiwei been recently?"},  # no events
    "20.4": {
        "zh": "记录一下小维今天吃了狗粮，还有提醒我明天带他去打疫苗",
        "en": "Record that Weiwei ate dog food today, and remind me to take him for vaccination tomorrow",
    },
}
