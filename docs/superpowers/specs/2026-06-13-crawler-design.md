# §6.1-6.2 爬虫模块详细设计

> 版本: v1.0 | 日期: 2026-06-13 | 状态: 已批准
> 基于: `2026-06-13-acm-agent-design.md` §6.1-6.2 细化

---

## 1. 设计决策总览

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 浏览器自动化 | DrissionPage | 国产库，双模式(HTTP+浏览器)，反爬友好 |
| 爬取策略 | HTTP 优先 + 浏览器降级 | 兼顾速度和稳定性 |
| 数据存储 | 文件中转（JSON） | 解耦爬虫与数据库，支持重试导入 |
| 速率限制 | 固定 QPS + 随机抖动 | 简单有效，防封禁 |
| 反爬 | 多层策略（UA/Cookie/延迟/浏览器指纹） | 应对不同平台反爬强度 |
| 导入策略 | Upsert 语义（幂等） | 支持重复导入不产生脏数据 |

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────┐
│                  crawlers/                       │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │  base.py │  │rate_limit│  │anti_detect│      │
│  │ (抽象基类)│  │ (速率控制)│  │ (反爬策略)│      │
│  └────┬─────┘  └──────────┘  └──────────┘      │
│       │                                          │
│  ┌────┴────────────────────────────────────┐    │
│  │  luogu.py  leetcode.py  nowcoder.py     │    │
│  │  codeforces.py  atcoder.py              │    │
│  └────┬────────────────────────────────────┘    │
│       │                                          │
│  ┌────▼─────┐                                   │
│  │ DrissionPage                                 │
│  │ SessionPage (HTTP 优先)                      │
│  │ ChromiumPage (浏览器降级)                     │
│  └──────────┘                                   │
└─────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────┐     ┌──────────────────┐
│  data/raw/       │────>│  PostgreSQL      │
│  {platform}/     │     │  (import 脚本)   │
│  {date}/         │     │                  │
│    problems.json │     │  problems        │
│    records.json  │     │  practice_records│
│    profiles.json │     │  platform_accounts│
└──────────────────┘     └──────────────────┘
```

**数据流**: 爬虫 → JSON 文件 → 导入脚本 → PostgreSQL

---

## 3. 基类设计（base.py）

### 3.1 CrawlResult 数据类

```python
@dataclass
class CrawlResult:
    """爬取结果容器"""
    success: bool
    data: dict | list | None = None
    error: str | None = None
    source: str = "http"  # "http" | "browser"
    retry_count: int = 0
```

### 3.2 RateLimiter 速率限制器

```python
class RateLimiter:
    """固定 QPS 速率限制器 + 随机抖动"""
    def __init__(self, qps: float, jitter: float = 0.3):
        self.interval = 1.0 / qps
        self.jitter = jitter
        self.last_time = 0.0

    def wait(self):
        now = time.monotonic()
        elapsed = now - self.last_time
        actual_interval = self.interval * (1 + random.uniform(-self.jitter, self.jitter))
        if elapsed < actual_interval:
            time.sleep(actual_interval - elapsed)
        self.last_time = time.monotonic()
```

### 3.3 BaseCrawler 抽象基类

```python
class BaseCrawler(ABC):
    """爬虫抽象基类"""
    PLATFORM: str  # 子类必须定义

    def __init__(self, data_dir: str = "data/raw", headless: bool = True):
        self.data_dir = Path(data_dir) / self.PLATFORM
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.http = SessionPage()
        self.browser: Optional[ChromiumPage] = None
        self.headless = headless
        self.limiter = RateLimiter(qps=self._default_qps())
        self._user_agents = self._load_user_agents()
        self._ua_index = 0

    def _default_qps(self) -> float: return 1.0
    def _load_user_agents(self) -> list[str]: ...
    def _rotate_ua(self) -> str: ...
    def _get_browser(self) -> ChromiumPage: ...

    def _http_request(self, url: str, **kwargs) -> CrawlResult:
        """HTTP 请求（优先）"""
        ...

    def _browser_request(self, url: str) -> CrawlResult:
        """浏览器请求（降级）"""
        ...

    def fetch_with_fallback(self, url: str, **kwargs) -> CrawlResult:
        """HTTP 优先，失败降级浏览器"""
        ...

    def save_json(self, data, filename: str, sub_dir: str = ""):
        """保存数据到 JSON 文件"""
        ...

    # 抽象方法
    @abstractmethod
    def fetch_user_profile(self, platform_uid: str) -> CrawlResult: ...
    @abstractmethod
    def fetch_user_records(self, platform_uid: str, since=None) -> CrawlResult: ...
    @abstractmethod
    def fetch_problem(self, source_id: str) -> CrawlResult: ...
    @abstractmethod
    def fetch_problems_by_tag(self, tag: str, count: int = 50) -> CrawlResult: ...
```

---

## 4. 5 平台实现

| 平台 | 类 | 主要数据源 | 反爬强度 | 默认 QPS |
|------|---|-----------|---------|---------|
| 洛谷 | `LuoguCrawler` | HTML + `_contentOnly=1` JSON | 中 | 2.0 |
| 力扣 | `LeetcodeCrawler` | GraphQL (`leetcode.cn/graphql`) | 强 | 1.0 |
| 牛客 | `NowcoderCrawler` | 内部 API + HTML | 中 | 2.0 |
| Codeforces | `CodeforcesCrawler` | REST API (`codeforces.com/api`) | 弱 | 5.0 |
| AtCoder | `AtcoderCrawler` | HTML + kenkoooo API | 弱 | 2.0 |

### 4.1 洛谷

- 用户: `GET /user/{uid}?_contentOnly=1` → JSON
- 记录: `GET /record/list?user={uid}&page={n}` → 分页
- 题目: `GET /problem/{id}?_contentOnly=1` → JSON
- 标签题: `GET /problem/list?type=TAG&page={n}` → 分页

### 4.2 力扣

- 用户: `POST /graphql` → `matchedUser` query
- 记录: `POST /graphql` → `recentAcSubmissionList` query
- 题目: `POST /graphql` → `question` query
- 需要 CSRF token: `GET /graphql` 响应头获取

### 4.3 牛客

- 用户: `GET /ac/programming-nojs/user/{uid}` → HTML 解析
- 记录: `GET /ac/programming-nojs/record?uid={uid}` → HTML
- 题目: `GET /ac/programming-nojs/problem/{id}` → HTML

### 4.4 Codeforces

- 用户: `GET /api/user.info?handles={uid}` → JSON
- 记录: `GET /api/user.status?handle={uid}&from=1&count=10000` → JSON
- 题目: `GET /api/problemset.problems?tags={tag}` → JSON
- **官方 API，无需浏览器降级**

### 4.5 AtCoder

- 用户: `GET /users/{uid}/history/json` → JSON (kenkoooo)
- 记录: `GET /api/results?user={uid}` → JSON (kenkoooo)
- 题目: `GET /problems` → HTML 解析

---

## 5. 反爬机制

### 5.1 五层策略

| 层 | 策略 | 实现 |
|---|------|------|
| L1 请求伪装 | UA 轮换 + Referer + Cookie | UA 池 + headers 管理 |
| L2 行为模拟 | 随机延迟 + 请求间隔抖动 | `jitter=0.3` |
| L3 浏览器指纹 | DrissionPage ChromiumPage | 真实浏览器，无 WebDriver 特征 |
| L4 代理轮换 | 预留接口 | `proxy_pool` 配置项 |
| L5 Cookie 管理 | 持久化 Cookie | `data/cookies/{platform}.json` |

### 5.2 Cookie 持久化

```python
class CookieManager:
    def __init__(self, cookie_dir: str = "data/cookies"):
        self.cookie_dir = Path(cookie_dir)
        self.cookie_dir.mkdir(parents=True, exist_ok=True)

    def save(self, platform: str, cookies: dict): ...
    def load(self, platform: str) -> dict | None: ...
    def is_expired(self, platform: str) -> bool: ...
```

### 5.3 DrissionPage 反爬优势

- **SessionPage**: 自动管理 Cookie，无 WebDriver 特征
- **ChromiumPage**: 控制真实浏览器，无 `navigator.webdriver` 标记，支持 JS 渲染

---

## 6. 文件中转与数据导入

### 6.1 目录结构

```
data/raw/
├── luogu/
│   ├── 2026-06-13/
│   │   ├── problems/
│   │   │   ├── P1001.json
│   │   │   └── P1002.json
│   │   ├── records/
│   │   │   └── user_12345.json
│   │   └── profiles/
│   │       └── user_12345.json
│   └── 2026-06-14/
├── leetcode/
├── nowcoder/
├── codeforces/
└── atcoder/
```

### 6.2 JSON 数据格式

**题目** (`problems/{id}.json`):
```json
{
  "source_platform": "luogu",
  "source_id": "P1001",
  "source_url": "https://www.luogu.com.cn/problem/P1001",
  "title": "A+B Problem",
  "difficulty_raw": "入门",
  "tags_platform": ["入门", "模拟"],
  "full_content": "题目完整内容...",
  "raw_detail": {}
}
```

**用户记录** (`records/{user}.json`):
```json
{
  "platform": "luogu",
  "platform_uid": "12345",
  "records": [
    {
      "platform_submission_id": "123456789",
      "problem_source_id": "P1001",
      "verdict_raw": "Accepted",
      "language": "C++",
      "submit_time": "2026-06-13T10:30:00+08:00",
      "runtime_ms": 12,
      "memory_kb": 1024
    }
  ]
}
```

### 6.3 导入脚本（幂等）

```python
class DataImporter:
    """JSON → PostgreSQL 导入器（upsert 语义）"""

    def __init__(self, prisma_client):
        self.db = prisma_client

    async def import_problems(self, platform: str, date: str) -> dict:
        """upsert 题目，返回 {imported, skipped, errors}"""
        ...

    async def import_records(self, platform: str, date: str) -> dict:
        """upsert 提交记录"""
        ...

    async def import_all(self, date: str = None) -> dict:
        """导入所有平台"""
        ...
```

---

## 7. 错误处理与重试

### 7.1 重试配置

```python
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    retryable_errors: set = {"HTTP 429", "HTTP 503", "HTTP 502", "timeout", "connection_error"}
```

### 7.2 执行器

```python
class CrawlerExecutor:
    def __init__(self, crawler: BaseCrawler, retry_config: RetryConfig = None): ...

    def execute(self, method_name: str, *args, **kwargs) -> CrawlResult:
        """执行爬虫方法，指数退避重试"""
        for attempt in range(self.config.max_retries + 1):
            result = method(*args, **kwargs)
            if result.success: return result
            if not should_retry(result, self.config): break
            time.sleep(calc_delay(attempt, self.config))
        return result
```

### 7.3 错误分类

| 错误类型 | 处理方式 |
|----------|---------|
| 网络超时 | 重试 3 次 |
| 限流 429 | 重试 + 增加间隔 |
| 服务不可用 | 重试 3 次 |
| 数据格式错误 | 记录日志，跳过 |
| 用户不存在 | 记录日志，标记无效 |
| 认证失败 | 停止，通知管理员 |

---

## 8. 统一入口与 CLI

### 8.1 双模式

```python
# python/crawlers/luogu.py
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["fetch_problems", "fetch_user", "fetch_records", "import"])
    parser.add_argument("--uid"); parser.add_argument("--tags"); parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--input", help="JSON (NestJS 调用模式)")
    args = parser.parse_args()

    if args.input:
        params = json.loads(args.input)
    else:
        params = vars(args)

    # 执行并输出 JSON 到 stdout
    print(json.dumps(result))
```

### 8.2 NestJS 调用

```typescript
// PythonService 通过 child_process.execFile 调用
execFile('python', ['/app/python/crawlers/luogu.py', '--input', JSON.stringify(params)])
```

### 8.3 批量爬取

```python
async def crawl_all_observed_users():
    """爬取所有观测用户 → 触发导入"""
    users = await get_observed_users()
    for user in users:
        for account in user.platform_accounts:
            crawler = get_crawler(account.platform)
            executor = CrawlerExecutor(crawler)
            result = executor.execute("fetch_user_records", account.platform_uid)
            if result.success:
                crawler.save_json(result.data, f"user_{account.platform_uid}.json", "records")
    await DataImporter(prisma).import_all()
```

---

## 9. 依赖项

```
# requirements.txt
DrissionPage>=4.0.0
```
