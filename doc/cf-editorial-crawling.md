# Codeforces Editorial 爬取方案

## 背景

CF editorial 页面结构为每个问题包含两个 spoiler：

```html
<div class="spoiler">
  <b class="spoiler-title">Tutorial</b>       <!-- 题解解释 -->
  <div class="spoiler-content">
    <div class="problemTutorial">Tutorial is loading...</div>
    <!-- ↑ 静态 HTML 中只有占位符，真实文本通过 JS AJAX 加载 -->
  </div>
</div>

<div class="spoiler">
  <b class="spoiler-title">Implementation</b> <!-- 代码 -->
  <div class="spoiler-content">
    <pre><code>// 实际代码在静态 HTML 中</code></pre>
  </div>
</div>
```

## 核心问题

CF 调用 `Codeforces.setupTutorials("/data/problemTutorial")` 在页面加载后通过 AJAX POST 请求动态加载 Tutorial 文本。`/data/problemTutorial` 端点需要有效的 CSRF Token + Session Cookie，系统 `curl` 无法获取。

静态 HTML 爬取只能拿到 Implementation 代码，Tutorial 解释文本完全丢失。

## 解决方案

### 方案：Scrapling Headless Browser

使用 [Scrapling](https://github.com/D4Vinci/Scrapling) 的 `StealthyFetcher`（基于 Patchright/Playwright Chromium）以 headless 模式加载 editorial 页面：

```python
from scrapling.fetchers import StealthyFetcher
page = StealthyFetcher.fetch(
    editorial_url + '?locale=en',
    headless=True,
    network_idle=True,   # 等待所有 AJAX 请求完成
    timeout=30_000,
)
```

`network_idle=True` 确保 Tutorial AJAX 请求完成后才返回，此时 `.spoiler-content` 中的 Tutorial 文本已从占位符替换为真实内容。

### 缓存策略

同一 contest 的所有题目共享一个 editorial 页面，使用两级缓存避免重复加载：

1. **Editorial URL 缓存** (`_editorial_url_cache`): `contest_id → editorial_url`，避免每个题目都调用 `_discover_editorial_url()` 扫描博客列表
2. **Rendered HTML 缓存** (`_editorial_cache`): `url → html`，同一个 contest 的后续题目直接复用已渲染的 HTML

缓存为类级别（class variable），线程安全（`threading.Lock`）。

### 解析流程 (`_parse_editorial_html`)

直接在 HTML 层面解析，不经过 Markdown 转换：

1. 找到第一个 `.ttypography`（主 editorial 内容，后续的 `.ttypography` 是用户评论）
2. 用 `<p><a href="/contest/{cid}/problem/{idx}">` 定位问题边界
3. 在每个问题边界之间：
   - **Tutorial spoiler**: 提取文本，清理 MathJax 格式（保留 `<nobr>` 文本，删除 Preview/script/MathML）
   - **Implementation spoiler**: 提取 `<pre>` 内代码（去除浏览器语法高亮 `<span>` 标签）
4. 构建 Markdown 格式的题解内容

### 去重方案

每个 CF 题目只有 1 篇 editorial 题解，固定 `solutionIndex = 0`。导入时：
- Upsert 使用 `(problemId, 0)` 唯一键
- 自动删除旧的、不同 solutionIndex 的残留行
- 防止爬取逻辑变更时产生重复题解

### 性能

| 操作 | 首次 | 缓存命中 |
|---|---|---|
| Editorial URL 发现（扫描博客列表） | ~4s | <10ms |
| 浏览器加载 + JS 执行 | ~8s | <10ms |
| HTML 解析 | ~200ms | ~200ms |

同一 contest 的 8 道题：首次 ~12s，后续每题 ~1.4s，总计 ~22s。

### 依赖

```
scrapling[all]==0.4.9
patchright==1.60.1     # Playwright fork with stealth patches
playwright==1.60.0
curl_cffi==0.15.0
msgspec==0.21.1
browserforge==1.2.4
```

## 回退策略

Scrapling 不可用时自动回退到静态 `curl` 抓取：
- 仍能提取 Implementation 代码
- Tutorial 部分显示提示信息，引导用户访问原页面

## 相关文件

| 文件 | 职责 |
|---|---|
| `python/crawlers/codeforces.py` | CF 爬虫主逻辑 |
| `backend/src/crawler/crawler.controller.ts` | 服务端导入 + 去重 |
| `backend/scripts/cleanup-cf-duplicate-solutions.ts` | 一次性清理历史重复数据 |
