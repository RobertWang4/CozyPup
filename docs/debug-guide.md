# Debug Guide: 按用户追踪错误

这些命令属于 `admin` CLI 的 `debug` 子组。完整 CLI 参考见
[`ADMIN_CLI.md`](ADMIN_CLI.md)；本文只讲"用户报了个 bug，怎么查"这条路径。

> 旧的顶层 `debug` 入口仍然可用，但只是一个转发到 `admin debug *` 的兼容 shim，
> 并会打印弃用提示。新脚本请直接用 `admin debug`。

## 快速上手

后端跑在 Google Cloud Run，日常排查在本地跑 CLI，读的是 Cloud Logging 和数据库：

```bash
cd backend
source .venv/bin/activate
admin login --dev --email you@example.com   # 生产环境用 `admin login` 走浏览器 OAuth
admin whoami
```

`admin debug trace` 需要 `gcloud auth application-default login`（它直接查 Cloud Logging）。

## 常用命令

### 1. 查看哪些用户出了问题

```bash
admin debug users                # 过去 24 小时，按用户分组的错误统计
admin debug users --since 7d
admin debug users --since 1h
```

输出示例：

```
USER ID                                  COUNT  LAST ERROR           LATEST MESSAGE
a1b2c3d4-e5f6-7890-abcd-ef1234567890        3  2026-03-25 10:30:00  Pet not found
anonymous                                    1  2026-03-25 09:15:00  Invalid token
```

### 2. 查看某个用户的所有错误

```bash
admin debug user a1b2c3d4-e5f6-7890-abcd-ef1234567890
admin debug user a1b2c3d4          # 前缀匹配，前几个字符就行
admin debug lookup you@example.com # 只有邮箱时先换成 user_id
```

输出示例：

```
Errors for user: a1b2c3d4-e5f6-7890-abcd-ef1234567890
Total: 3 (showing last 20)

  [2026-03-25 10:30:00] db/DatabaseError
    Pet not found
    → GET /api/v1/pets/999
    trace: req-abc123def456

  [2026-03-25 10:25:00] agent_llm/AgentError
    LLM timeout after 30s
    → POST /api/v1/chat
    trace: req-789xyz000111
```

### 3. 查看某个错误的完整详情

从上面拿到 `trace: req-xxx`，然后：

```bash
admin debug trace req-abc123def456
```

输出包括：时间、用户、错误类型、完整 traceback、请求数据。round 0 的
`llm_request` 里带着完整 `messages` 数组（图片换成占位符），所以任何一条 trace
都能离线重放。

### 4. 按条件筛选错误

```bash
admin debug errors --module app.routers.chat --last 20
admin debug errors --user a1b2c3d4
admin debug errors --module app.agents --user a1b2c3d4 --last 5
```

### 5. 其他命令

```bash
admin debug modules --since 24h              # 按模块统计错误数
admin debug summary --since 24h              # 按错误指纹分组（找重复错误）
admin debug requests --user <user_id> --last 10
admin debug tokens --user <user_id> --period 7d
admin debug replay req-abc123def456          # 重放失败的请求
admin debug generate-test req-abc123def456   # 从错误自动生成回归测试
```

## 典型排查流程

```
用户报 bug
  ↓
admin debug users --since 24h          # 找到出问题的用户
  ↓
admin debug user <user_id>             # 看该用户所有错误
  ↓
admin debug trace <correlation_id>     # 看某个错误的完整 traceback
  ↓
admin debug replay <correlation_id>    # 重现问题
  ↓
admin debug generate-test <cid>        # 生成回归测试
```

需要更全面的用户画像（订阅、宠物、活动、最近错误一次看全）时用
`admin user inspect <email|id>`。

## 日志位置

- **Error snapshots**: `backend/logs/error_snapshots/*.json`
- **应用日志**: `gcloud logging read "resource.type=cloud_run_revision AND
  resource.labels.service_name=backend" --limit=20 --project=cozypup-39487`
- **结构化日志字段**: 每行 JSON 都包含 `correlation_id`、`user_id`、`pet_id`
- **Trace 归档**: sink `cozypup-trace-sink` 把 `cozypup.trace` 永久复制到
  `gs://cozypup-traces`；`python scripts/export_traces.py` 导出成按 session 的 JSONL

## 查看已注册用户

日志系统只记录错误。要按人查就用 CLI：

```bash
admin user search <query>
admin user inspect <email>
```

要直接查库，用 Supabase Console 的 SQL Editor：

```sql
SELECT id, email, name, provider, created_at
FROM users ORDER BY created_at DESC;
```
