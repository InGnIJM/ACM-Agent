# 五平台统一题目渲染 — 设计规格

> 2026-06-17 | 状态：设计中

## 1. 目标

用 Python 爬虫抓取 LeetCode CN、Codeforces、NowCoder、AtCoder 四个平台题目（洛谷复用现有爬虫），存入 PostgreSQL（复用 Prisma Problem 表），前端用 Material Design 3 风格渲染成统一详情页。五个平台内容兼容展示。

## 2. 范围

**本次交付：** 5 道示例题（每个平台 1 道）完整爬取入库 + 前端详情页渲染。

| 平台 | URL | sourceId |
|---|---|---|
| 洛谷 | `https://www.luogu.com.cn/problem/P6412` | `P6412` |
| LeetCode CN | `https://leetcode.cn/problems/regular-expression-matching/description/` | `regular-expression-matching` |
| NowCoder | `https://ac.nowcoder.com/acm/problem/317391` | `317391` |
| Codeforces | `https://codeforces.com/problemset/problem/2234/G` | `2234/G` |
| AtCoder | `https://atcoder.jp/contests/DEGwer2023/tasks/1202Contest_j` | `1202Contest_j` |

## 3. 架构

```
python/crawlers/<platform>.py   → 独立爬虫脚本，输出统一 JSON
python/crawler_runner.py        → 入口，遍历 5 题，调后端 API 入库
backend/src/problem/            → 已有模块，提供 GraphQL 查询 + REST API
frontend/src/pages/             → 统一题目详情页
```

不依赖旧爬虫代码（除洛谷外），不依赖旧前端渲染路径。

## 4. 数据模型

### 4.1 统一 JSON（爬虫输出）

每个爬虫输出结构：

```json
{
  "title": "Regular Expression Matching",
  "sourcePlatform": "leetcode",
  "sourceId": "regular-expression-matching",
  "sourceUrl": "https://leetcode.cn/problems/regular-expression-matching/description/",
  "difficultyRaw": "Hard",
  "difficultyNormalized": 7.0,
  "tagsNormalized": ["string", "dynamic-programming", "recursion"],
  "tagsPlatform": { "topicTags": ["String", "Dynamic Programming", "Recursion"] },
  "rawDetail": {
    "description": "<p>给你一个字符串 s 和一个字符规律 p...</p>",
    "inputFormat": "<p>第一行...</p>",
    "outputFormat": "<p>输出...</p>",
    "samples": [
      { "input": "aa\na", "output": "false", "note": "解释：a 无法匹配 aa" }
    ],
    "note": "<p>提示：0 <= s.length <= 20</p>",
    "timeLimit": "2s",
    "memoryLimit": "256MB"
  }
}
```

### 4.2 Prisma 映射

| 统一 JSON 字段 | Prisma Problem 字段 | 说明 |
|---|---|---|
| `title` | `title` | |
| `sourcePlatform` | `sourcePlatform` | enum 值 |
| `sourceId` | `sourceId` | |
| `sourceUrl` | `sourceUrl` | |
| `difficultyRaw` | `difficultyRaw` | |
| `difficultyNormalized` | `difficultyNormalized` | 0-10 归一化 |
| `tagsNormalized` | `tagsNormalized` | 统一标签 |
| `tagsPlatform` | `tagsPlatform` | 平台原始标签 |
| `rawDetail` | `rawDetail` | 完整平台数据 |
| `rawDetail.*` → Markdown | `fullContent` | 统一渲染 Markdown |

**难度归一化规则：**

| 平台 | 原始值 | 归一化 |
|---|---|---|
| 洛谷 | "入门"/"普及-"/.../"NOI/NOI+/CTSC" | 已有逻辑 |
| LeetCode | "Easy"/"Medium"/"Hard" | 2/5/8 |
| Codeforces | 数字 800-3500 | /350 |
| NowCoder | 无明确难度 | 默认 5 |
| AtCoder | 无/分值 | 暂默认 5 |

### 4.3 现有 Schema 字段使用说明

`rawDetail`（Json）存储所有平台特定的原始数据，前端直接从 rawDetail 取值渲染。`fullContent`（Text）存储预处理后的完整 Markdown，给 Markdown 组件直接渲染。两个字段互补：rawDetail 提供结构化数据（如样例的 input/output 对），fullContent 提供完整的内容流。

## 5. 爬虫设计

### 5.1 LeetCode CN

LeetCode 有 GraphQL API：`POST https://leetcode.cn/graphql/`

使用 `questionTitle`、`questionContent`（中文）、`questionDetail` 等 query。请求时带 `Referer` 和 `Content-Type: application/json`。questionContent 返回 HTML，需转 Markdown。

### 5.2 Codeforces

CF 有官方 API：`https://codeforces.com/api/contest.standings?contestId=2234&from=1&count=1` + `problemset.problems` 接口。

或直接解析页面 HTML（SSR 渲染，数据在 `<script>` JSON 中）。

### 5.3 NowCoder

HTML 解析（SSR）。题目内容在 `<div class="terminal-topic">` 中。标签从页面 meta 或分类链接提取。

注意：NowCoder 页面有 U+200B 零宽空格残留（已知 bug，memory 已记录），需清理。

### 5.4 AtCoder

HTML 解析（SSR）。日文+英文双语的页面，优先取 `<span class="lang-en">` 英文内容。标题在 `<title>` 或 `<h2>` 中。

### 5.5 洛谷

复用现有 `python/crawlers/luogu.py`，无需改动。

## 6. 后端

### 6.1 导入 API

新增端点 `POST /problems/import`，接收统一 JSON，upsert 到 Problem 表（按 `sourcePlatform + sourceId` 唯一约束）。

### 6.2 查询 API

已有 `GET /problems/:id` 返回问题详情，需确认返回结构包含 `rawDetail` 和 `fullContent`。

## 7. 前端

### 7.1 路由

`/problems/:platform/:sourceId` → `ProblemDetail.tsx`

### 7.2 组件树

```
ProblemDetailPage (新)
├── PlatformBadge          — MUI Chip: 平台图标 + 名称
├── DifficultyChip         — MUI Chip: 难度颜色区分
├── ProblemTitle           — MUI Typography h4
├── MetaBar                — 时间限制、内存限制、标签
├── Tabs (MUI)             — 描述 | 输入格式 | 输出格式 | 样例 | 备注
│   ├── TabPanel: Markdown — 复用 Markdown 组件
│   └── TabPanel: Samples  — 每个样例并列展示 Input/Output
```

### 7.3 MD3 风格适配

项目已使用 MUI v5（Material Design 2.7），MD3 主要差异在于调色板和圆角：

- `theme.ts` 中启用 MD3 token：TonalPalette、Shape Scale
- Card 圆角：12px / 16px
- Elevated 阴影替代 Outlined 边框
- 背景色：`surface-container-low` 替代 `grey.100`

实际效果：MUI v5 的 `createTheme` 已部分支持 MD3 token（v5.10+）。通过调整 `shape.borderRadius`、`palette.tonalOffset` 等参数即可接近 MD3 风格，无需迁移到 MUI v6。

## 8. 错误处理

- 爬虫网络失败：重试 3 次，间隔 2s
- API 写入失败：打印错误 JSON，不中断批量
- 前端数据缺失：`rawDetail` 为空时显示 "暂无内容"
- Markdown 渲染异常：fallback 展示原始文本

## 9. 测试策略

| 层 | 测试 |
|---|---|
| 爬虫 | 每个爬虫跑一次，比对输出 JSON 结构是否符合统一 schema |
| 导入 | 测试 upsert 逻辑（新建 + 更新） |
| 前端 | 渲染 5 道题，截图/肉眼验证 |

## 10. 不做什么

- 不做批量列表爬取（仅 5 题）
- 不做题解爬取（仅题目详情）
- 不做向量嵌入
- 不改动现有 ProblemDetail.tsx（新建独立页面，并行对比）
