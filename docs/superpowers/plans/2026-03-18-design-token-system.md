# PetPal 令牌化设计体系 (Tokenized Design System)

## Context

PetPal 目前有一个静态 HTML demo (`demos/petpal-full-demo.html`)，其中定义了 ~57 个 CSS 自定义属性（颜色、字体、间距、阴影等）。项目即将进入 React 实现阶段，需要一个结构化的 Design Token 系统来：
1. 将设计决策从代码中解耦，存储为 JSON
2. 支持 Pencil MCP 的双向同步（设计工具 ↔ 代码）
3. 为未来主题切换（暗色模式）打基础
4. 提供 TypeScript 类型安全

## 架构概览

```
JSON Token Files (W3C DTCG 格式)
        │
        ├─→ resolve.ts (别名解析 + 展平)
        │       │
        │       ├─→ inject.ts (运行时注入 CSS 变量到 :root)
        │       └─→ types.ts (生成 TypeScript 类型)
        │
        └─→ sync-pencil-tokens.ts (双向同步 Pencil .pen 变量)
```

**三层 Token 层级：**
- **Primitive** — 原始值（色板 `#FFF8F0`、尺寸 `20px`、字体族）
- **Semantic** — 语义映射（`bg` → `{color.cream.50}`）
- **Component** — 组件级覆盖（`bubble.user.bg` → `{accent}`）

运行时全部展平为 CSS 自定义属性，前缀 `--pp-`。

## 文件结构

```
frontend/src/tokens/
  primitives/
    color.tokens.json          # 色板（从 demo 提取）
    typography.tokens.json     # fontFamily / fontSize / fontWeight / lineHeight
    spacing.tokens.json        # 4px 倍数间距
    radius.tokens.json         # 圆角
    shadow.tokens.json         # 阴影原始值
    animation.tokens.json      # duration + easing
  semantic/
    color.tokens.json          # bg / surface / text / accent 等语义色
    typography.tokens.json     # heading / body / caption 语义排版
    elevation.tokens.json      # card / drawer / modal 语义阴影
  components/
    bubble.tokens.json         # 聊天气泡
    card.tokens.json           # Record/Map/Email 卡片
    header.tokens.json         # 顶栏
    input.tokens.json          # 输入框
    drawer.tokens.json         # 抽屉
    banner.tokens.json         # 急症横幅
    switch.tokens.json         # Toggle 开关
  themes/
    light.tokens.json          # 默认 Warm Organic
    dark.tokens.json           # 未来暗色主题（占位）
  resolve.ts                   # 核心：递归解析 {alias}，输出扁平 Map
  inject.ts                    # 运行时 CSS var 注入
  types.ts                     # [生成] TypeScript token 类型
  index.ts                     # 聚合导出
frontend/scripts/
  generate-token-types.ts      # 类型生成脚本
  sync-pencil-tokens.ts        # Pencil 双向同步
```

## Token JSON 格式（W3C DTCG 2025.10）

### Primitive 示例
```json
{
  "$type": "color",
  "color": {
    "cream": {
      "50":  { "$value": "#FFF8F0" },
      "200": { "$value": "#F0E6DA" }
    },
    "orange": {
      "500": { "$value": "#E8835C", "$description": "Primary accent" }
    }
  }
}
```

### Semantic 示例（引用 Primitive）
```json
{
  "bg":      { "$type": "color", "$value": "{color.cream.50}" },
  "accent":  { "$type": "color", "$value": "{color.orange.500}" },
  "text":    { "$type": "color", "$value": "{color.brown.900}" }
}
```

### Component 示例（引用 Semantic）
```json
{
  "bubble": {
    "user": {
      "bg":   { "$type": "color", "$value": "{accent}" },
      "text": { "$type": "color", "$value": "{color.white}" }
    }
  }
}
```

## 组件消费方式：CSS Modules + CSS Vars

```css
/* ChatBubble.module.css */
.user {
  background: var(--pp-bubble-user-bg);
  color: var(--pp-bubble-user-text);
  border-radius: var(--pp-radius-xl);
}
```

不引入 CSS-in-JS 运行时，Vite 原生支持 CSS Modules，Capacitor WebView 完全兼容。

## Pencil MCP 集成

| 方向 | 说明 |
|------|------|
| DTCG → Pencil | 将语义 token 转为 Pencil `{ type, value }` 格式，写入 `.pen` 文件的 `variables` |
| Pencil → DTCG | 从 `.pen` 读取变量变更，回写到 `semantic/*.tokens.json` |

Pencil 的 MCP 服务端暴露 canvas context 给 Claude Code，token JSON 与 `.pen` 变量结构对齐后，AI 可以精确读取设计意图而非猜测像素。

## 实施步骤

### Step 1: 创建 Primitive Token 文件
从 `demos/petpal-full-demo.html` 的 57 个 CSS 变量中提取原始值，按类别拆分到 `primitives/*.tokens.json`。

### Step 2: 创建 Semantic Token 文件
将 demo 中的语义名（`--bg`, `--accent`, `--bubble-user`）映射为 `{alias}` 引用。

### Step 3: 实现 `resolve.ts`
递归遍历 JSON，解析 `{path}` 别名，输出扁平 `Record<string, string>` CSS var 映射。含循环引用检测。

### Step 4: 实现 `inject.ts`
在 `main.tsx` 启动时调用，将 resolved tokens 设为 `document.documentElement.style` 属性。支持 `switchTheme()` 热切换。

### Step 5: 实现类型生成脚本
`scripts/generate-token-types.ts` → 生成 `types.ts`，导出 `TokenKey` union type 和 `token()` 辅助函数。

### Step 6: 创建 Component Token 文件 + 首个组件
从 ChatBubble 开始，创建 `components/bubble.tokens.json` + `ChatBubble.module.css`，验证渲染与 demo 一致。

### Step 7: Pencil 同步脚本
`scripts/sync-pencil-tokens.ts`，先实现 DTCG → Pencil 单向，再加反向同步。

### Step 8: 暗色主题占位
`themes/dark.tokens.json` 只覆盖语义 token，`switchTheme('dark')` 热切换验证。

## 验证方式

1. 启动 `npm run dev`，打开浏览器，检查 `:root` 上的 CSS 变量是否与 demo 一致
2. 用 DevTools 修改一个 `--pp-*` 变量，验证所有引用该变量的组件同步更新
3. 运行 `npm run generate:tokens`，检查 `types.ts` 包含所有 token key
4. TypeScript 编译无误，`token('--pp-nonexistent')` 应报编译错误
5. 主题切换：调用 `switchTheme('dark')`，验证 CSS vars 全量更新
