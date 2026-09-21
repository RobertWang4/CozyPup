# CozyPup

[![CI](https://github.com/RobertWang4/CozyPup/actions/workflows/ci.yml/badge.svg)](https://github.com/RobertWang4/CozyPup/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![scope: backend](https://img.shields.io/badge/scope-backend-orange.svg)](#架构)

[English](README.md) | **中文**

> **本仓库是后端。** SwiftUI iOS 客户端在另一个私有仓库，通过 TestFlight 分发；两端如何衔接见 [架构](#架构)。

AI 宠物健康助手。一个聊天界面搞定一切——记录事件、管理宠物档案、找附近宠物医院、设提醒。没有表单，没有按钮，没有引导流程。用户说话，AI 执行。

后端跑在 Google Cloud Run，iOS 应用走 TestFlight 分发。

## 截图

<p align="center">
  <img src="docs/media/chat-voice-input.png" width="200" alt="主页 — 语音输入">
  <img src="docs/media/chat-record-and-places.png" width="200" alt="聊天 — 事件记录 + 地点搜索">
  <img src="docs/media/place-detail-card.png" width="200" alt="地点详情卡片（含评价）">
  <img src="docs/media/calendar-timeline.png" width="200" alt="日历时间线">
</p>

## 结果

下面每个数字都能在本仓库里复现，来源逐行标注，没有一个是推算的。

| 指标 | 结果 | 来源 |
|---|---|---|
| Agent 回归套件 `pass^2`（18 个精选场景，每个跑两次，两次都过才算过） | **94%**，LangGraph 迁移前是 83% | [`docs/agent-request-flow.md`](docs/agent-request-flow.md#迁移结果) |
| 紧急分类器（微调 Qwen3-0.6B，Q8 量化） | **F1 0.948** — 召回 0.982，精确率 0.917 | [`backend/nano/README.md`](backend/nano/README.md) |
| …对比它要替换的关键词正则 | F1 0.47 — 召回 0.375，精确率 0.636 | 同上 |
| 分类器延迟，4 线程（Cloud Run 侧车预算：p95 < 300ms） | p50 20ms / p95 22ms | 同上 |
| 知识检索 top-1 / top-3（中文，n=60） | 88.3% / 96.7% | [`backend/eval_history/`](backend/eval_history/) |
| 知识检索 top-1 / top-3（英文，n=30） | 93.3% / 100% | 同上 |
| 安全红线用例（用药剂量 / 确诊 / 人用药） | 14 / 14 通过 | 同上 |
| 单元测试 | 650 通过，9 跳过，行覆盖率 62% | `pytest tests --ignore=tests/e2e --cov=app` |

## 架构

```
 iOS (SwiftUI，私有仓库)                        ChatView → ChatStore → ChatService
        │  SSE: token / thinking / card / emergency / done
        ▼
 FastAPI   POST /api/v1/chat ── EventSourceResponse
   Phase 0  会话 + 消息落库（每用户每天一个 session）
   Phase 1  并行预处理：语言检测、紧急正则、nano 分类器、
            意图提取 → SuggestedAction(工具, 参数, 置信度)
   Phase 2  组装 prompt，静态 → 动态排列以命中前缀缓存
            + MemWeaver 检索（pgvector：用户记忆 ∪ 全局知识）
   Phase 3  LangGraph agent 图，MAX_ROUNDS = 5：

              START → prepare → model ──有工具调用──→ tools ──→ model
                                  │                     │
                                  │ 无                  ├─延后─→ confirm ⇄
                                  ▼                     ▼    (interrupt)
                                review ──重试──→      finalize → END

   Phase 4  不阻塞响应：档案提取、记忆同步、上下文压缩

 Postgres (Supabase) — 业务表 + pgvector + LangGraph checkpoint
 侧车      llama-server on :8081 — Qwen3-0.6B 紧急分类器
```

### 受约束 Agent 的核心思路

**LLM 的输出被当作建议，而不是命令。** 每一个工具调用都要过一层能拒绝它、能修它的代码：schema 校验返回错误列表而不是抛异常，错误作为 tool result 喂回去，模型下一轮自己改参数；归属检查让写错 `pet_id` 这件事不可能发生；破坏性调用一律延后，绝不凭模型一句话就执行。在这之前还有一个确定性正则预处理器，它把带置信度的 `SuggestedAction` 挂进 prompt，所以模型漏掉一个显而易见的写操作时 `review` 节点能催它，催了还不做就由后处理器直接执行高置信度动作。整个循环没有一处依赖模型自觉——这才是便宜模型（DeepSeek V4.1 Flash）也能准到可以上线的原因，而更强的模型（`gpt-5`）只留给紧急情况。

2026-09 起这个循环从手写 `while` 换成了 **LangGraph** 图。最大的收益是确认门控：破坏性调用先把自己停在一边，这一轮照常跑完（模型还能用上同一轮里其他工具的真实结果），然后 `interrupt()` 把整个图状态 checkpoint 进 Postgres。用户点确认，用那个 thread `Command(resume=True)` 恢复，执行**预存的参数**——不再问模型，所以"LLM 改口"不可能发生。完整走查见 [`docs/agent-request-flow.md`](docs/agent-request-flow.md)。

### 这套东西买到了什么

| 问题 | 朴素的 LLM + 工具 | 这里 |
|---|---|---|
| 模型说"已记录"但没调工具 | 静默丢数据 | write-claim nag，再不行由后处理器执行 |
| 模型给了非法日期格式 | 工具崩 | 校验器拒绝，模型下一轮自己改对 |
| 模型把"遛狗 + 洗澡"合成一个事件 | 丢数据 | `plan` 工具强制拆步，plan nag 盯完成 |
| 模型忘了调 `search_places` | "我不知道附近有什么医院" | nudge 带着明确指令重试一轮 |
| 用户说"删掉我的宠物" | 立刻删 | 延后 → 确认卡 → `interrupt` → 用预存参数恢复 |
| "我的狗在抽搐" | 泛泛而谈 | 分类器 + 正则 → 升级模型 → `trigger_emergency` |

## 有意思的部分

**微调的紧急路由器**（`backend/nano/`）——Qwen3-0.6B 的 LoRA 微调，判断一句话是不是真的危急、值不值得切贵模型。做法是一次前向后读 `true` / `false` 两个 token 的 logprob，所以拿到的是概率而不是标签，阈值可以往召回那边调。导出成 GGUF、Q8 量化，作为 llama-server 侧车容器和后端一起部署在 Cloud Run 上。`app/agents/emergency_clf.py` 按四档 flag 合并它和老正则的结论（`off` → `shadow` → `union` → `clf`），线上是 **`shadow`**：模型照样调、照样记日志，但路由还是正则做，两边不一致的 case 带 `disagree=true` 记下来，喂给下一轮训练。`nano/` 里的 README 是按教学笔记写的：606 条人工核过的考卷、为什么准确率是错的指标、以及模型每一轮学到的捷径（r1："短的就是 false"；r2："名字 + 吐了 = true"）和修掉它的最小对比对。

**Eval harness**（`backend/app/agent_harness/`）——场景驱动，打真实后端。确定性阅卷器（`graders.py`）检查调了哪些工具、哪些真的执行了、卡片类型、数据库副作用；代码查不了的文本质量交给 LLM judge（`judge.py`），它的 system prompt 里写进了产品自己的约定，所以不会因为"回复太短"就把一个正确的回答判失败。`--repeat N` 配 `--baseline` 得到 `pass^2`，用来把真实回归和模型抖动分开；`report.py` 会标出任何相比上一份报告掉了通过率的场景。18 个精选场景，另有 354 个从旧 e2e 套件迁移过来。

**MemWeaver 记忆 + 知识**（`backend/app/memory/`）——一次 pgvector 查询就 UNION 出用户自己的 `behavioral` / `cognitive` 记忆节点和全局 `knowledge` 切片，按物种和 cosine distance 过滤，behavioral 命中再按新鲜度加权。日历的写入和删除会同步维护自己的记忆节点。两种用法：直接作为 prompt 上下文，以及作为 `search_knowledge` 工具——后者返回一张 references 卡片，App 里可以点开。

**Admin CLI**（`backend/app/admin_cli/`）——`admin` 是真正在用的运维入口：查用户、发/退订阅、封号、feature flag、清限流和踢登录、按 correlation id 重放整条请求管线。每一次写操作都会在 `admin_audit_log` 留一行，记操作人和必填的 `--reason`。见 [`docs/ADMIN_CLI.md`](docs/ADMIN_CLI.md)。

**33 个工具**，覆盖日历、宠物、提醒、地点、每日任务、知识，以及控制类（`plan`、`request_images`、`set_language`）；其中 5 个需要用户确认。

## 安装与运行

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # 只跑生产的话去掉 [dev]
```

创建 `backend/.env`（参考 `.env.example`）。跑通聊天循环的最小集合：

| 变量 | 说明 |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://…`，生产用 Supabase session pooler |
| `MODEL_API_BASE` / `MODEL_API_KEY` | `MODEL` 的 OpenAI 兼容端点（默认 `deepseek/deepseek-flash`） |
| `JWT_SECRET` | 任何不是默认值的值 |

可选：`EMERGENCY_MODEL` 及其独立的 `EMERGENCY_MODEL_API_BASE` / `_API_KEY`；`EMBEDDING_API_KEY`（记忆和知识检索）；`GOOGLE_PLACES_API_KEY`（医院/美容店搜索）；`EMERGENCY_CLF_URL`（启用分类器侧车）；`APNS_*`（推送）；`DOUBAO_*`（流式语音输入）；`GCS_BUCKET`（头像上传）。

```bash
alembic upgrade head                         # 迁移
uvicorn app.main:app --reload --port 8000    # 起服务
ruff check app                               # lint
pytest tests --ignore=tests/e2e              # 单元测试（不需要数据库和 API key）
docker build -t cozypup-backend .            # Cloud Build 部署的同一个镜像
```

Eval 打真实后端，会花真实 token：

```bash
agent eval scenarios/agent --env prod --repeat 2 --report reports/run.json
python -m nano.cli eval --predictor keyword           # 分类器基线
```

## 文档

- [`docs/agent-request-flow.md`](docs/agent-request-flow.md) — 一条消息的完整旅程：图、状态、确认 interrupt
- [`docs/ADMIN_CLI.md`](docs/ADMIN_CLI.md) — 运维 CLI 完整参考
- [`docs/debug-guide.md`](docs/debug-guide.md) — 从用户报 bug 到生成回归测试
- [`backend/nano/README.md`](backend/nano/README.md) — 分类器微调，按教学笔记写的
- [`CLAUDE.md`](CLAUDE.md) — 工作笔记：约定、部署、加新工具的 checklist
- `web-demo/` — iOS 各屏的静态 HTML 稿（设计参考，不连后端）

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI、SQLAlchemy 2（async）、Alembic、LangGraph、LiteLLM |
| 数据库 | Supabase 上的 PostgreSQL（session pooler）+ pgvector |
| LLM | DeepSeek V4.1 Flash（聊天）· `gpt-5`（紧急）· Qwen3-0.6B LoRA（路由）· `text-embedding-3-small` |
| iOS（私有） | SwiftUI、Combine、MapKit、EventKit、Speech |
| 平台 | Cloud Run（蒙特利尔）、Cloud Build、Secret Manager、GCS、APNs |
| 认证 | Apple 登录、Google 登录、JWT |

## 许可

MIT，见 [LICENSE](LICENSE)。
