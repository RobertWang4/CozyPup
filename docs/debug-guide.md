# Debug Guide: 按用户追踪错误

## 快速上手

SSH 到服务器后，进入项目目录即可使用 `debug` 命令。

```bash
ssh ubuntu@168.138.75.153
cd /path/to/backend
```

## 常用命令

### 1. 查看哪些用户出了问题

```bash
# 过去 24 小时，按用户分组的错误统计
debug users

# 过去 7 天
debug users --since 7d

# 过去 1 小时
debug users --since 1h
```

输出示例：
```
USER ID                                  COUNT  LAST ERROR           LATEST MESSAGE
a1b2c3d4-e5f6-7890-abcd-ef1234567890        3  2026-03-25 10:30:00  Pet not found
anonymous                                    1  2026-03-25 09:15:00  Invalid token
```

### 2. 查看某个用户的所有错误

```bash
# 用完整 user_id
debug user a1b2c3d4-e5f6-7890-abcd-ef1234567890

# 或者只用前缀（前几个字符就行）
debug user a1b2c3d4
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
debug trace req-abc123def456
```

输出包括：时间、用户、错误类型、完整 traceback、请求数据。

### 4. 按条件筛选错误

```bash
# 按模块筛选
debug errors --module app.routers.chat --last 20

# 按用户筛选
debug errors --user a1b2c3d4

# 组合筛选
debug errors --module app.agents --user a1b2c3d4 --last 5
```

### 5. 其他命令

```bash
# 按模块统计错误数
debug modules --since 24h

# 按错误指纹分组（找重复错误）
debug summary --since 24h

# 重放失败的请求
debug replay req-abc123def456

# 从错误自动生成测试
debug generate-test req-abc123def456
```

## 典型排查流程

```
用户报 bug
  ↓
debug users --since 24h          # 找到出问题的用户
  ↓
debug user <user_id>             # 看该用户所有错误
  ↓
debug trace <correlation_id>     # 看某个错误的完整 traceback
  ↓
debug replay <correlation_id>    # 重现问题
  ↓
debug generate-test <cid>        # 生成回归测试
```

## 日志位置

- **Error snapshots**: 服务器上 `logs/error_snapshots/*.json`
- **应用日志**: `docker compose logs -f backend`
- **结构化日志字段**: 每行 JSON 都包含 `correlation_id`、`user_id`、`pet_id`

## 查看已注册用户

日志系统只记录错误。要看所有用户，查数据库：

```bash
# 通过 Neon Console: https://console.neon.tech → SQL Editor
SELECT id, email, name, provider, created_at
FROM users ORDER BY created_at DESC;
```
