# Phase 3: 爬虫模块 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans

**Goal:** 实现 5 平台爬虫（DrissionPage 双模式）+ 反爬 + 文件中转（JSON）+ 导入器，90% 测试覆盖率

**Architecture:** BaseCrawler 抽象基类 → 5 平台实现 → JSON 文件存储 → DataImporter 幂等写入 PostgreSQL

**Tech Stack:** Python 3.11+, DrissionPage, httpx, pytest, pytest-cov

---

## 文件结构

```
python/
├── requirements.txt
├── crawlers/
│   ├── __init__.py
│   ├── base.py              # BaseCrawler, RateLimiter, CrawlResult, CookieManager
│   ├── luogu.py
│   ├── leetcode.py
│   ├── nowcoder.py
│   ├── codeforces.py
│   ├── atcoder.py
│   ├── importer.py           # DataImporter (JSON→DB upsert)
│   ├── batch_crawl.py
│   ├── test/
│   │   ├── __init__.py
│   │   ├── test_base.py
│   │   ├── test_luogu.py
│   │   ├── test_leetcode.py
│   │   ├── test_cf.py
│   │   ├── test_rate_limiter.py
│   │   ├── test_cookie_manager.py
│   │   └── test_importer.py
├── data/
│   ├── raw/      # JSON 输出
│   └── cookies/  # Cookie 持久化
```

---

## Task 1: 基础设施 — BaseCrawler + RateLimiter + CookieManager

**Files:** Create `python/crawlers/base.py`, `python/crawlers/test/test_base.py`

- [ ] **Step 1: 写测试**

```python
# python/crawlers/test/test_base.py
import pytest
import time
from unittest.mock import MagicMock, patch
from crawlers.base import RateLimiter, CrawlResult, CookieManager

class TestRateLimiter:
    def test_wait_under_qps(self):
        rl = RateLimiter(qps=10, jitter=0)  # 100ms interval
        start = time.monotonic()
        for _ in range(5):
            rl.wait()
        elapsed = time.monotonic() - start
        assert 0.35 <= elapsed <= 0.55  # 4×100ms = 400ms ± jitter

    def test_jitter_adds_variance(self):
        rl = RateLimiter(qps=1.0, jitter=0.5)
        intervals = []
        for _ in range(3):
            t0 = time.monotonic()
            rl.wait()
            intervals.append(time.monotonic() - t0)
        assert not all(abs(i - intervals[0]) < 0.01 for i in intervals)  # not all equal

class TestCrawlResult:
    def test_success_defaults(self):
        r = CrawlResult(success=True, data={"key": "val"})
        assert r.success
        assert r.data == {"key": "val"}
        assert r.source == "http"
        assert r.retry_count == 0

    def test_failure(self):
        r = CrawlResult(success=False, error="timeout", retry_count=2)
        assert not r.success
        assert r.error == "timeout"

class TestCookieManager:
    def test_save_and_load(self, tmp_path):
        cm = CookieManager(cookie_dir=str(tmp_path))
        cm.save("luogu", {"token": "abc123"})
        assert cm.load("luogu") == {"token": "abc123"}

    def test_load_nonexistent_returns_none(self, tmp_path):
        cm = CookieManager(cookie_dir=str(tmp_path))
        assert cm.load("nonexistent") is None

    def test_is_expired_true_when_no_cookie(self, tmp_path):
        cm = CookieManager(cookie_dir=str(tmp_path))
        assert cm.is_expired("luogu")
```

- [ ] **Step 2: 运行确认失败**

```bash
cd python && pip install -r requirements.txt
pytest crawlers/test/test_base.py -v
# 预期: FAIL
```

- [ ] **Step 3: 实现**

```python
# python/crawlers/base.py
import time, random, json, logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from DrissionPage import SessionPage, ChromiumPage

logger = logging.getLogger(__name__)

@dataclass
class CrawlResult:
    success: bool
    data: dict | list | None = None
    error: str | None = None
    source: str = "http"
    retry_count: int = 0

class RateLimiter:
    def __init__(self, qps: float, jitter: float = 0.3):
        self.interval = 1.0 / max(qps, 0.1)
        self.jitter = jitter
        self.last_time = 0.0
    def wait(self):
        now = time.monotonic()
        elapsed = now - self.last_time
        actual = self.interval * (1 + random.uniform(-self.jitter, self.jitter))
        if elapsed < actual:
            time.sleep(actual - elapsed)
        self.last_time = time.monotonic()

class CookieManager:
    def __init__(self, cookie_dir: str = "data/cookies"):
        self.cookie_dir = Path(cookie_dir)
        self.cookie_dir.mkdir(parents=True, exist_ok=True)
    def save(self, platform: str, cookies: dict):
        (self.cookie_dir / f"{platform}.json").write_text(json.dumps(cookies))
    def load(self, platform: str) -> dict | None:
        p = self.cookie_dir / f"{platform}.json"
        return json.loads(p.read_text()) if p.exists() else None
    def is_expired(self, platform: str) -> bool:
        return self.load(platform) is None

class BaseCrawler(ABC):
    PLATFORM: str

    def __init__(self, data_dir: str = "data/raw", headless: bool = True):
        self.data_dir = Path(data_dir) / self.PLATFORM
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.http = SessionPage()
        self.browser: Optional[ChromiumPage] = None
        self.headless = headless
        self.limiter = RateLimiter(qps=self._default_qps())
        self._ua_index = 0

    def _default_qps(self) -> float: return 1.0

    def _get_browser(self) -> ChromiumPage:
        if self.browser is None:
            self.browser = ChromiumPage(headless=self.headless)
        return self.browser

    def _http_request(self, url: str, **kwargs) -> CrawlResult:
        try:
            self.limiter.wait()
            resp = self.http.get(url, **kwargs)
            if resp.status_code == 200:
                ct = resp.headers.get('content-type', '')
                data = resp.json() if 'json' in ct else resp.text
                return CrawlResult(success=True, data=data, source="http")
            return CrawlResult(success=False, error=f"HTTP {resp.status_code}")
        except Exception as e:
            return CrawlResult(success=False, error=str(e))

    def _browser_request(self, url: str) -> CrawlResult:
        try:
            self.limiter.wait()
            page = self._get_browser()
            page.get(url)
            return CrawlResult(success=True, data=page.html, source="browser")
        except Exception as e:
            return CrawlResult(success=False, error=str(e))

    def fetch_with_fallback(self, url: str, **kwargs) -> CrawlResult:
        result = self._http_request(url, **kwargs)
        if result.success: return result
        logger.warning(f"HTTP failed {url}: {result.error}, fallback to browser")
        return self._browser_request(url)

    def save_json(self, data, filename: str, sub_dir: str = "") -> Path:
        date_str = datetime.now().strftime("%Y-%m-%d")
        dir_path = self.data_dir / date_str / sub_dir if sub_dir else self.data_dir / date_str
        dir_path.mkdir(parents=True, exist_ok=True)
        filepath = dir_path / filename
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Saved {filepath}")
        return filepath

    @abstractmethod
    def fetch_user_profile(self, platform_uid: str) -> CrawlResult: ...
    @abstractmethod
    def fetch_user_records(self, platform_uid: str, since=None) -> CrawlResult: ...
    @abstractmethod
    def fetch_problem(self, source_id: str) -> CrawlResult: ...
    @abstractmethod
    def fetch_problems_by_tag(self, tag: str, count: int = 50) -> CrawlResult: ...
```

- [ ] **Step 4: 运行测试**

```bash
pytest crawlers/test/test_base.py -v
# 预期: 全部 PASS
git add python/
git commit -m "feat(crawler): add BaseCrawler, RateLimiter, CookieManager with tests"
```

---

## Task 2: 5 平台爬虫实现

**Files:** Create `python/crawlers/luogu.py`, `leetcode.py`, `nowcoder.py`, `codeforces.py`, `atcoder.py`

- [ ] **Step 1: 写测试 — Codeforces（最容易，官方 API）**

```python
# python/crawlers/test/test_cf.py
from unittest.mock import patch, MagicMock
from crawlers.codeforces import CodeforcesCrawler

def test_cf_fetch_user_returns_success():
    crawler = CodeforcesCrawler()
    crawler._http_request = MagicMock(return_value=CrawlResult(success=True, data={"result": [{"handle": "tourist"}]}))
    result = crawler.fetch_user_profile("tourist")
    assert result.success
    assert result.source == "http"

def test_cf_fetch_user_records():
    crawler = CodeforcesCrawler()
    crawler._http_request = MagicMock(return_value=CrawlResult(success=True, data={"result": []}))
    result = crawler.fetch_user_records("tourist")
    assert result.success

def test_cf_qps():
    assert CodeforcesCrawler()._default_qps() == 5.0
```

- [ ] **Step 2: 实现 5 平台爬虫**

```python
# python/crawlers/codeforces.py
class CodeforcesCrawler(BaseCrawler):
    PLATFORM = "codeforces"
    API = "https://codeforces.com/api"
    def _default_qps(self): return 5.0
    def fetch_user_profile(self, uid): return self._http_request(f"{self.API}/user.info?handles={uid}")
    def fetch_user_records(self, uid, since=None): return self._http_request(f"{self.API}/user.status?handle={uid}&from=1&count=1000")
    def fetch_problem(self, sid): return self._http_request(f"{self.API}/problemset.problems")
    def fetch_problems_by_tag(self, tag, count=50): return self._http_request(f"{self.API}/problemset.problems?tags={tag}")
```

```python
# python/crawlers/luogu.py — 类似模式，BASE_URL="https://www.luogu.com.cn"，_default_qps=2.0
# python/crawlers/leetcode.py — GRAPHQL_URL，qps=1.0
# python/crawlers/nowcoder.py — qps=2.0
# python/crawlers/atcoder.py — KENKOO_API，qps=2.0
```

- [ ] **Step 3: 运行全部爬虫测试**

```bash
pytest crawlers/test/ -v
git commit -m "feat(crawler): add 5 platform crawler implementations"
```

---

## Task 3: CrawlerExecutor（重试） + DataImporter（导入）

- [ ] **Step 1: 写 retry + import 测试**
- [ ] **Step 2: 实现 CrawlerExecutor（指数退避重试 3 次）+ DataImporter（upsert 幂等导入）**
- [ ] **Step 3: 覆盖率检查**

```bash
pytest crawlers/ --cov=crawlers --cov-report=term-missing
# 预期: ≥ 90%
git commit -m "feat(crawler): add retry executor and data importer"
```

---

## Phase 3 Gate

| 检查项 | 标准 |
|--------|------|
| BaseCrawler | 4 个抽象方法可被子类覆盖 |
| RateLimiter | QPS + 抖动正常工作 |
| 5 平台 | 各自 fetch_user_profile/records/problem 返回 CrawlResult |
| 重试 | 429/503/超时触发重试，3 次上限 |
| 导入 | upsert 幂等 |
| 覆盖率 | ≥ 90% |
