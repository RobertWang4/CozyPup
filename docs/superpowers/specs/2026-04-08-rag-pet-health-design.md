# RAG 宠物健康问答设计

## 概述

为 CozyPup 添加 RAG（检索增强生成），提升宠物健康问答的准确性。AI 回答健康问题时，检索外部知识库（专业病例/医疗资料）+ 用户历史记录（就医、用药、日历事件），结合宠物档案给出更精准的建议。

## 核心决策

| 决策项 | 方案 |
|--------|------|
| 数据源 | 外部知识库 + 用户历史，两者并行检索 |
| 触发方式 | LLM 通过 function calling 调用 `search_knowledge` 工具 |
| Embedding 写入 | 实时异步（chat post-processing 阶段） |
| Embedding 模型 | OpenAI text-embedding-3-small via LiteLLM（1536 维） |
| 检索架构 | 单工具统一检索，内部并行查两个索引 |
| 问诊引导 | Prompt + 知识条目里的问诊模板驱动，按需提问不强制 |
| 图片识别 | 已有能力，prompt 层整合 |
| 引用展示 | References 卡片按钮 → 点击弹出 drawer 显示引用列表 |
| 宠物档案 | 已在 system prompt 中注入，不需要额外 embedding |

## 数据模型

### Embedding 表（已有，扩展 source_type）

现有 `Embedding` 表，`source_type` 枚举新增 `'knowledge_base'`：

```
现有: 'chat_turn', 'daily_summary', 'calendar_event'
新增: 'knowledge_base'
```

- 外部知识条目：`user_id = NULL`（全局共享），`source_id` 指向 `KnowledgeArticle.id`
- 用户历史条目：`user_id` + 可选 `pet_id`，`source_id` 指向原始记录

### KnowledgeArticle 表（新增）

存储外部知识库的原始文章，和 Embedding 分开管理：

```python
class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    id: UUID
    title: str                    # "犬呕吐的常见原因与处理"
    content: TEXT                  # 全文内容
    category: str                 # "消化系统" / "皮肤" / "疫苗" / ...
    species: str                  # "dog" / "cat" / "all"
    url: str | None               # 原文链接（引用用）
    metadata_json: JSON           # 灵活字段
    created_at: datetime
    updated_at: datetime
```

## 工具定义

### search_knowledge

```python
{
    "name": "search_knowledge",
    "description": (
        "检索宠物健康知识库和用户历史记录。\n"
        "【必须调用】用户描述宠物健康问题、症状、疾病、用药、饮食疑问时。\n"
        "不要用于: 闲聊、创建日程、记录事件。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，描述症状或问题"
            },
            "pet_id": {
                "type": "string",
                "description": "相关宠物ID，可选。明确知道是哪只宠物时传入"
            },
            "species": {
                "type": "string",
                "enum": ["dog", "cat"],
                "description": "物种，用于过滤知识库"
            }
        },
        "required": ["query"]
    }
}
```

## 检索流程

```
search_knowledge(query="狗呕吐", pet_id=xxx, species="dog")
  │
  ├─ embed(query) → 1536 维向量
  │
  ├─ 并行查询:
  │   ├─ 外部知识:
  │   │   WHERE source_type = 'knowledge_base'
  │   │     AND (species = 'dog' OR species = 'all')
  │   │   ORDER BY cosine_similarity DESC
  │   │   LIMIT 3, threshold > 0.7
  │   │
  │   └─ 用户历史:
  │       WHERE user_id = xxx
  │         AND (pet_id = yyy OR pet_id IS NULL)  -- 未指定宠物时查所有
  │         AND source_type IN ('calendar_event', 'daily_summary')
  │       ORDER BY cosine_similarity DESC
  │       LIMIT 3, threshold > 0.7
  │
  └─ 返回:
      {
        "knowledge": [
          {
            "title": "犬呕吐常见原因与处理",
            "content": "... 相关段落 ...",
            "url": "https://...",
            "triage_questions": ["呕吐物颜色？", "频率？"]
          }
        ],
        "history": [
          {
            "date": "2026-03-15",
            "content": "维尼拉肚子，去了第一个医院",
            "event_id": "uuid"
          }
        ]
      }
```

### 多宠物隔离

- LLM 传入 `pet_id` 时，历史数据只查该宠物
- `pet_id` 为空时，查该用户所有宠物的历史，LLM 结合上下文判断
- 外部知识库无 `pet_id`，按 `species` 过滤

## Embedding 写入流程

### 用户历史 — 实时异步

在 chat post-processing（Phase 4）新增一步：

```python
# orchestrator 返回后，异步执行，不阻塞 SSE 响应
asyncio.create_task(generate_embeddings(
    user_id=user_id,
    session_id=session_id,
    # 对本轮对话摘要做 embedding
    # 如果本轮创建了日历事件，对事件内容也做 embedding
))
```

- 失败静默记 log，不影响用户体验
- 避免重复：按 (source_type, source_id) 去重

### 外部知识库 — CLI 批量导入

```bash
# 导入单篇
python -m app.rag.ingest --file knowledge/dog_vomiting.md --species dog --category 消化系统

# 批量导入
python -m app.rag.ingest --dir knowledge/ --species dog

# 查看状态
python -m app.rag.ingest --stats
```

### Chunk 策略

- 按段落切分，每 chunk 约 300-500 字
- 保留标题上下文：每个 chunk 前缀加文章标题 + 章节标题
- 问诊模板部分整块存，不拆分

## 问诊引导机制

**Prompt 驱动，不是硬编码流程。**

### 知识条目里包含问诊模板

```markdown
# 犬呕吐
## 问诊问题
1. 呕吐物颜色和质地？（黄色液体/白色泡沫/食物残渣/带血）
2. 呕吐频率和持续时间？
3. 近期饮食变化或可能误食？
4. 精神状态？（活泼/萎靡/拒食）
5. 其他伴随症状？（腹泻/发热/抖）

## 判断逻辑
- 黄色液体 + 单次 + 精神好 → 可能空腹过久，建议...
- 带血 + 任意 → 紧急，建议立即就医
```

### System prompt 指令

> 当用户描述健康问题时，用 search_knowledge 检索。根据返回的问诊问题和用户已提供的信息判断：
> - 如果关键信息已经足够，直接给建议
> - 如果缺少关键信息，逐个询问（每次一个问题，提供选项方便快速回答）
> - 用户说"跳过/直接告诉我/算了"时，根据已有信息立即给结论
> - 如果用户发了图片，先从图片提取信息，减少需要问的问题

### 图片配合

已有图片处理能力（base64 注入 LLM 消息）。LLM 看到图片后：
1. 从图片提取可见症状信息
2. 将观察到的特征作为检索 query 的一部分
3. 图片已提供的信息不需要再问

## iOS 端：References 卡片

### SSE 事件

```
event: card
data: {
  "type": "references",
  "items": [
    {"title": "犬呕吐常见原因与处理", "url": "https://...", "source": "knowledge"},
    {"title": "2026-03-15 就医记录", "event_id": "uuid", "source": "history"}
  ]
}
```

### UI 交互

1. AI 文字回答正常输出
2. 回答结束后，如果有引用，显示一个小按钮："📎 References"
3. 点击弹出 bottom drawer，显示引用列表：
   - `source: "knowledge"` → 点击用 SFSafariViewController 打开 url
   - `source: "history"` → 点击跳转到 app 内日历事件详情

### 样式

- 按钮：`Tokens.fontCaption` + `Tokens.textSecondary` + `Tokens.surface` 背景
- Drawer：`Tokens.surface2` 背景，列表项用 `Tokens.fontSubheadline`
- 圆角：`Tokens.radiusSmall`

## 文件变更清单

### 新增文件

```
backend/app/rag/
├── __init__.py
├── embeddings.py       # embedding 生成（调用 OpenAI API via LiteLLM）
├── retrieval.py        # 向量检索逻辑（并行查知识库+历史）
├── ingest.py           # CLI 批量导入知识库
└── chunker.py          # 文章切分策略

backend/knowledge/      # 外部知识库文件（后续填充）
└── README.md
```

### 修改文件

```
backend/app/models.py                    # 新增 KnowledgeArticle 模型，扩展 EmbeddingSourceType 枚举
backend/app/agents/tools/definitions.py  # 新增 search_knowledge 工具定义
backend/app/agents/tools/knowledge.py    # 新增 search_knowledge handler
backend/app/agents/tools/__init__.py     # 注册新工具
backend/app/agents/validation.py         # 新增 search_knowledge 参数校验
backend/app/agents/locale.py             # 新增工具描述翻译 + decision tree 规则
backend/app/agents/prompts_v2.py         # 新增问诊引导指令
backend/app/agents/orchestrator.py       # Phase 4 新增 embedding 生成任务
backend/app/config.py                    # 新增 EMBEDDING_MODEL 配置

ios-app/CozyPup/Models/SSEEvent.swift    # 新增 references card 类型
ios-app/CozyPup/Views/Chat/ReferencesCard.swift  # References 按钮 + Drawer 视图
ios-app/CozyPup/Views/Chat/ChatBubble.swift      # 集成 references card 渲染
```

### 数据库迁移

```
alembic revision --autogenerate -m "add knowledge_articles table and extend embedding source_type"
```

## 依赖

无新增 Python 依赖。Embedding API 通过现有 LiteLLM 调用，pgvector 已安装。

## 数据源（后续填充）

知识库数据源暂不确定，RAG pipeline 设计为可插拔：
- CLI 脚本支持 markdown 文件批量导入
- `KnowledgeArticle` 表存原始文章，Embedding 表存向量
- 以后无论是爬取、采购、还是 AI 生成的知识，都通过 CLI 脚本灌入即可
