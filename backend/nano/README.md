# nano — 紧急路由分类器：微调教学笔记

目标：训一个 Qwen3-0.6B 的 LoRA 微调模型，输入用户一句话，输出 `true`（十分危急，切高级模型）或 `false`。
替换现在 `app/agents/emergency.py` 里的关键词正则。

## 一、微调到底在做什么

一个语言模型就是"给一段文字，预测下一个字的概率分布"。
微调 = 拿我们自己的（题目 → 标准答案）数据，反复做一件事：

1. 把题目喂进去，让模型算出"下一个字"的概率，比如 `true` 0.3、`false` 0.7
2. 标准答案是 `true`，loss = −log(0.3)。模型给正确答案的概率越低，loss 越大
3. 反向传播：算出每个参数往哪个方向挪一点能让 P(true) 变大，挪一小步
4. 换下一批题，重复。全部题过一遍叫一个 epoch，一般过 2 到 3 遍

注意它**不是**"让模型答一遍、判对错、再调"。训练只看概率，是连续的；"答对答错"是评估时才算的。

**LoRA**：原模型几亿个参数全冻住不动，在每个注意力/MLP 矩阵旁边挂一对小矩阵 A、B（宽度叫 rank，我们用 8），只训这对小矩阵。
好处：便宜、快、不容易把底座学坏。训完可以把 A×B 加回原矩阵，得到一个和原模型一样大的新模型，推理零额外开销。
限制：rank 8 只能教"格式和判断习惯"，教不了新知识。我们的任务正好只需要判断习惯。

**核心原则**：模型学的是你给它的数据分布。线上会遇到什么，训练集里就得有什么；没见过的它会瞎猜。
所以整套流程 70% 的功夫在数据，训练本身是最简单的一步。

## 二、文件与职责

```
backend/nano/
├── contract.py         任务定义：prompt 模板 + 标签词。训练/评估/线上唯一来源
├── data/
│   ├── seeds.yaml      考卷：606 条人工核过的题（手写 124 + E2E 468 + 场景 14 + 线上 3）
│   ├── GEN_BRIEF.md    出题说明：给生成子代理看的判定标准、风格要求、格式
│   ├── gen/*.yaml      练习题：17 个子代理按主题生成，约 5000 条
│   ├── train.jsonl     练习题合并去重后 90%（由 build_dataset.py 生成）
│   └── val.jsonl       练习题 10%，训练时用来看有没有过拟合
├── check_data.py       数据体检：能否解析、标签是不是 bool、重复、每文件统计
├── build_dataset.py    合并 gen/ → train/val，并把和考卷重复的题剔掉
├── predictors.py       考生：keyword（现有正则）、QwenPredictor（原版或微调后的模型）
├── evaluate.py         阅卷：召回/精确率/F1、阈值扫描、错题列表、写 JSON 报告到 reports/
├── cli.py              命令入口：python -m nano.cli eval --predictor keyword|qwen
│
├── train.py            LoRA 训练（教程级注释）
├── export.py           merged → GGUF f16 → Q8 量化
└── serve/grammar.gbnf  llama-server 语法文件，只允许生成 true/false（Dockerfile 待写）
```

### contract.py 为什么单独一个文件

模型看到的是字节。训练时 prompt 是 A，线上 prompt 是 A 加一个空格，效果就会掉。
所以 system prompt、标签词、few-shot 例子只写在这一个地方，谁要用都从这里 import。

### predictors.py 里 P(true) 是怎么算的

不让模型"生成"一个词，而是：
1. 用 `contract.build_messages` 拼 prompt，套上 Qwen 的对话模板，关掉 thinking 模式
2. 前向一次，取最后一个位置的 logits（对词表里每个词的打分）
3. 只看 `true` 和 `false` 这两个词的分数，做 softmax，得到 P(true)

好处：一次前向、零解码、延迟最低；而且给的是概率，阈值可以调。
宁可多误报也不漏判，就把阈值往下调。关键词正则做不到这种权衡。

### evaluate.py 看什么

- **召回**（recall）= 真危急里抓到了多少。漏一个真危急可能害了一条狗，这是第一指标
- **精确率**（precision）= 报警的里面多少是真的。误报只是多花一次贵模型的钱
- 阈值扫描：0.1 到 0.9 每档的召回/精确率，选线上用哪个阈值
- 错题列表：MISS（漏报）排前面，FALSE_ALARM 排后面。错题按 tag 分桶就知道该补哪类数据

准确率（accuracy）没用：606 题只有 56 条 true，全答 false 准确率也有 91%。

## 三、步骤、意义、现状

### 步骤 0：定义任务 —— 已完成
输入一句话，输出 bool，只有十分危急才 true。判定标准写在 `seeds.yaml` 头部和 `GEN_BRIEF.md`。
意义：合同定错了后面全白干。改合同 = 重新造数据。

### 步骤 1：先建考卷 —— 已完成
`seeds.yaml`，606 题，人工核过。它是尺子，所以要人核，不能让模型打标。
它**不进训练集**。练习题和考卷重叠，考出来的分数就是假的（build_dataset.py 会剔重）。

### 步骤 2：跑基线 —— 进行中
让还没训的考生先考一次，知道起点在哪：

| 考生 | 召回 | 精确率 | 说明 |
|---|---|---|---|
| keyword（线上现状） | 0.375 | 0.636 | F1 0.47，漏 35/56 |
| Qwen3-0.6B 零样本 | 0.375 | 0.875 | 只给 prompt 不训 |
| Qwen3-0.6B 少样本 | 0.304 | 0.773 | 6 个例子反而更差 |
| 微调 r1 | 0.893 | 0.980 | F1 0.935。漏短句：训练集短句 0 条 true |
| 微调 r2 | 0.964 | 0.635 | 补了 300 短 true 后矫枉过正，学了"名字+吐了=true" |
| **微调 r3** | **0.982** | **0.917** | **F1 0.948**，加最小对比对后通过。Q8 量化后分数不变，p95 22ms |

意义：没有基线就没法说"效果好"；零样本能不能写出合法 true/false 决定底座选得对不对；
少样本回答"要不要训"——如果塞几个例子就够，就不用训。顺便先把阅卷代码在不训的模型上跑通，
训完就不会把评估 bug 当模型问题。

### 步骤 3：造练习题 —— 进行中
17 个子代理按主题生成，每个主题一个文件，约 5000 条：
- 正例 ~1700：抽搐/呼吸/中毒食物/中毒药物/外伤/消化泌尿/模糊恐慌，一半以上不含关键词
- 负例 ~3800：轻微症状/关键词陷阱/记录/提醒/档案/查询/其他工具/闲聊边缘/复合长句/纯英文

意义：
- 分布匹配：线上是语音转文字的口语，练习题也必须是
- 难负例：关键词陷阱（"狗吃葡萄会怎样"）是正则错得最多的地方，要专门造
- 日常流量占大头：这是精确率的来源
- 为什么 5000：0.6B + rank 8 学一个二分类，几千条够；再多边际收益小

之后：`python -m nano.check_data` 体检 → 抽 100 条人看 → `python -m nano.build_dataset` 出 train/val。

### 步骤 4：训练 —— 已完成（r1/r2/r3，见上表）
`train.py`：transformers + peft + trl，Mac 上用 MPS，同一脚本到 GPU 服务器不用改。

超参起始值：

| 参数 | 值 | 含义 |
|---|---|---|
| rank | 8 | 小矩阵宽度，越大学得越多也越容易背题 |
| learning rate | 1e-4 | 每步挪多少 |
| epochs | 3 | 数据过几遍 |
| batch size | 16 | 一次看几题 |
| max length | 256 | 超长截断，我们的题都很短 |

只对答案那一个 token 算 loss，题目部分 mask 掉（模型不需要学怎么写题）。

看两条曲线：train loss 和 val loss。一起降是正常；train 继续降 val 开始升 = 过拟合（背题），
停在 val 最低的 checkpoint。loss 数值本身没意义，只用来比较轮次。

### 步骤 5：阅卷 + 错题分析 —— 已完成
用同一个 `evaluate.py` 考微调后的模型，和四行基线放一张表。
错题按 tag 分桶。错误集中在哪类 → **加那类数据**回到步骤 3，不是调超参。90% 的问题在数据。

### 步骤 6：导出、量化、测延迟 —— 已完成（`python -m nano.export --run r3`，Mac 4 线程 p50 20ms / p95 22ms）
adapter 合并进底座 → 转 GGUF → Q8 量化。量化会损失精度，小模型更敏感，**量化后重新阅卷**。
本地 `llama-server` 限 4 线程模拟 Cloud Run，测 p50/p95，目标 p95 < 300ms（单 token 输出，只有 prefill）。

### 步骤 7：上线 —— 代码已写，待部署（`app/agents/emergency_clf.py`、`nano/serve/Dockerfile`、根目录 `cloudbuild.yaml` 双容器）
llama-server 作为 backend 的 sidecar 容器。flag 分四档：
off（现状）→ shadow（只记日志不路由，跑一周看和正则不一致的谁对）→ union（正则 or 模型，只增召回）→ clf（模型为主，超时回落正则）。
不一致的 case 导出、人看、加进下一轮训练集。这是模型长期变好的唯一途径。

## 四、常见的坑
- 训练集和线上分布不一致（书面语 vs 语音口语）
- 考卷和练习题重叠 → 分数虚高
- 只看准确率，不看召回
- 一上来调超参，其实是数据问题
- **模型永远学最省力的表面特征**：r1 学了"短 = false"，r2 学了"名字 + 吐了 = true"。每轮训练前跑 `check_data` 末尾的形状体检，
  补数据要造最小对比对（`小维吐了` false / `小维吐血了` true），形状相同只有内容不同，模型才没捷径可走
- Mac MPS 训练：batch 长度必须固定 + 每步 `torch.mps.empty_cache()`，否则内存无限涨；屏幕睡眠会让 GPU 降速，开 `caffeinate -dims'
- 量化后忘了重新评估
- 训练和线上 prompt 差一个空格

## 五、常用命令
```bash
cd backend
python -m nano.check_data                                   # 数据体检
python -m nano.cli eval --predictor keyword                 # 关键词基线
python -m nano.cli eval --predictor qwen                    # 原版 0.6B 零样本
python -m nano.cli eval --predictor qwen --fewshot          # 少样本
python -m nano.build_dataset                                # gen/ → train.jsonl / val.jsonl
PYTORCH_ENABLE_MPS_FALLBACK=1 python -m nano.train --run r3  # LoRA 训练，约 30 分钟
python -m nano.cli eval --predictor qwen --model nano/models/r3/merged
python -m nano.export --run r3                              # → clf-f16.gguf, clf-q8.gguf
llama-server -m nano/models/r3/clf-q8.gguf -c 512 -t 4 --port 8081 --grammar-file nano/serve/grammar.gbnf
python -m nano.cli eval --predictor llama --name r3_q8      # 量化后重考 + 延迟
```
