# 数据生成简报（所有生成子代理必读）

## 任务
为 CozyPup（AI 宠物健康助手 App）的**紧急路由分类器**生成训练数据。每条数据是一句用户发给 App 的消息，加一个 bool 标签：

- `true`  = 十分危急，答错代价高，要切到高级模型处理
- `false` = 其他一切

分类器**不做医学判断**，只判断"这句话像不像下面的危急清单"。

## 判定标准（只有明确危急才 true）
**true**：
- 危及生命的体征：呼吸困难/张口呼吸/舌头发紫、抽搐、倒地不起、昏迷叫不醒、牙龈发白、大量出血、腹部胀硬+干呕、公猫尿不出、中暑瘫软
- 误食明确有毒/危险物（正在发生）：大量巧克力、葡萄/葡萄干、木糖醇、人用药、鼠药、百合（猫）、防冻液、消毒液、针线/骨头卡住、夏威夷果、洋葱大量
- 严重外伤：车撞、高坠、咬伤出血不止、大面积烫伤、眼球脱出
- 急剧恶化：吐血/便血 + 精神差、多症状叠加 + 趴着不动、幼崽/老年动物持续恶化
- 主人明显恐慌 + 任一严重体征描述（哪怕措辞模糊）
- 别人的宠物**正在**求助（"朋友的狗刚被车撞了问我怎么办"）

**false**：
- 单一轻微症状：吐一次/软便/喷嚏/轻微跛行/挠痒/眼屎/毛球/食欲略降/喝水多
- 记录类：吃了什么、遛了、洗澡、称重、打疫苗、驱虫、看医生、换粮
- 提醒/任务：提醒喂药、每天遛狗、下周打针
- 档案：建档、改生日/性别/体重/品种、换头像、总结档案
- 查询：查日历、上次驱虫、疫苗周期、喂养/训练/行为知识
- **关键词陷阱**：假设/科普提问（"狗吃葡萄会怎样"）、过去的事（"去年中过毒"）、已确诊在治疗（"癫痫在吃药"）、别人的宠物非求助、新闻/视频
- 事后记录（"帮我记一下今天抽搐了"）→ false，标 gray
- 找店、写邮件、切语言、问 App 能干嘛、纠正、删除、确认、"对"、"不是这个"
- 闲聊、夸、吐槽、打招呼、谢谢、测试机器人、无关话题
- 剂量极小的误食（"舔了一口巧克力"）→ false，标 gray
- 灰区默认 false，加 `gray`

## 风格（最重要）
用户大多用**语音转文字**或手机随手打。必须模仿：
- 没标点，或标点乱、全是空格分隔
- 同音错字：吐→兔、拉稀→拉西、喘→船、抽搐→抽出/抽出来、呼吸→呼息、办→半、咪咪→米米
- 口头禅：那个、就是、然后、呃、啊、哎、完了完了
- 一句连着说不断句、说一半改口、重复
- 结尾"怎么办呀""咋办""要不要去医院""正常吗"
- 长短混合：2 个字到 60 个字都要有
- 宠物名多样：豆豆、咪咪、维尼、小维、团子、花花、球球、旺财、Max、Luna、Whiskers、Mochi，也有不叫名字的"我家狗""猫猫""他""它"
- 物种：狗猫为主，少量兔子/仓鼠/鸟/龟
- **约 25% 英文**，英文也要口语（no caps, no punctuation, "like", "kinda"）
- **不要书面语，不要医学术语堆砌，不要每句都完整主谓宾**

## 输出格式（YAML 列表，严格照此）
```yaml
- msg: 豆豆突然就倒了然后一直抽 嘴里有白沫子 怎么办啊怎么办
  label: true
  tags: [seizure, voice, panic]
  why: 正在发作

- msg: 狗狗今天有点兔 兔的白色的
  label: false
  tags: [mild, typo, voice]
  why: 单次轻微
```
- `msg` 含冒号、引号、`#` 时用双引号包起来
- `tags` 从词表选 1-4 个：seizure breathing toxin trauma bleeding gdv urinary shock heat neuro panic mild record reminder task profile question knowledge places email language correction delete confirm chitchat past hypothetical other_owner managed multi gray typo voice en keyword_trap edge
- `why` ≤ 12 个字
- 每条 msg 必须彼此不同，也不能抄下面的示例

## 质量规则
- 标签按判定标准来，拿不准就 false + gray
- true 里**至少一半不含**这些词：抽搐 中毒 呼吸困难 seizure poison breathing（要用描述而不是关键词）
- false 里要有 15% 左右"看起来吓人其实不紧急"的关键词陷阱
- 同一个意思换 5 种以上说法，别只换宠物名
- 写完用 `python -c "import yaml,sys;d=yaml.safe_load(open(sys.argv[1]));print(len(d),sum(x['label'] for x in d))" <文件>` 自检能解析且数量对

## 示例（风格参考，禁止照抄）
```yaml
- msg: 米米一直张着嘴船气 舌头那个颜色有点紫
  label: true
  tags: [breathing, voice, typo]
  why: 猫张口呼吸发紫
- msg: 我降压药掉地上了被狗捡着吃了 就刚刚
  label: true
  tags: [toxin, voice]
  why: 人用药误食
- msg: 那个 我家狗 就是 突然倒地上了 现在起不来 呃 眼睛翻白
  label: true
  tags: [neuro, voice]
  why: 倒地不起
- msg: got hit by a car he's awake but bleeding from the mouth
  label: true
  tags: [trauma, bleeding, en, voice]
  why: 车祸出血
- msg: 豆豆刚吐了一口 没事 精神挺好的
  label: false
  tags: [mild, voice]
  why: 单次呕吐
- msg: 狗吃葡萄会咋样
  label: false
  tags: [question, hypothetical, keyword_trap, voice]
  why: 假设提问
- msg: 上个月抽搐过一次 医生说是癫痫 现在在吃药
  label: false
  tags: [past, managed, keyword_trap]
  why: 已在治疗
- msg: 今天维尼去公园玩了 跑了一下午
  label: false
  tags: [record, voice]
  why: 日常活动
- msg: 每天提醒我晚上八点喂药
  label: false
  tags: [reminder, voice]
  why: 提醒
- msg: 把维尼的生日改成三月五号
  label: false
  tags: [profile, voice]
  why: 改档案
- msg: 附近有啥宠物医院
  label: false
  tags: [places, gray, voice]
  why: 只是找店
- msg: 又拆家了 拖鞋咬烂了第三双
  label: false
  tags: [chitchat, voice]
  why: 吐槽
- msg: 帮我记录一下，小维今天抽搐发作了
  label: false
  tags: [record, gray, keyword_trap]
  why: 事后记录
- msg: 豆豆刚偷吃了一小口巧克力蛋糕 就指甲盖那么点
  label: false
  tags: [toxin, gray, keyword_trap, voice]
  why: 剂量极小
- msg: max ate like a tiny piece of my chocolate chip cookie
  label: false
  tags: [toxin, gray, keyword_trap, en, voice]
  why: 剂量极小
```
