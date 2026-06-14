"""
Tests for crawlers/base.py – CrawlResult, RateLimiter, CookieManager,
BaseCrawler, CrawlerExecutor, RetryConfig, DataImporter.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from abc import ABC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crawlers.base import (
    BaseCrawler,
    CookieManager,
    CrawlerExecutor,
    CrawlResult,
    DataImporter,
    RateLimiter,
    RetryConfig,
)


# ═══════════════════════════════════════════════
# CrawlResult
# ═══════════════════════════════════════════════

class TestCrawlResult:
    """Tests for the CrawlResult dataclass."""

    def test_defaults(self) -> None:
        r = CrawlResult(success=True)
        assert r.success is True
        assert r.data is None
        assert r.error is None
        assert r.source == "http"
        assert r.retry_count == 0

    def test_custom_values(self) -> None:
        r = CrawlResult(
            success=False,
            data={"a": 1},
            error="timeout",
            source="browser",
            retry_count=2,
        )
        assert r.success is False
        assert r.data == {"a": 1}
        assert r.error == "timeout"
        assert r.source == "browser"
        assert r.retry_count == 2

    def test_data_can_be_list(self) -> None:
        r = CrawlResult(success=True, data=[1, 2, 3])
        assert r.data == [1, 2, 3]

    def test_bool_true(self) -> None:
        assert bool(CrawlResult(True)) is True

    def test_bool_false(self) -> None:
        assert bool(CrawlResult(False)) is False

    def test_is_ok_success_with_data(self) -> None:
        r = CrawlResult(True, data={"k": "v"})
        assert r.is_ok is True

    def test_is_ok_success_without_data(self) -> None:
        r = CrawlResult(True)
        assert r.is_ok is False

    def test_is_ok_failure(self) -> None:
        r = CrawlResult(False, data={"k": "v"})
        assert r.is_ok is False

    def test_is_ok_none_data(self) -> None:
        r = CrawlResult(True, data=None)
        assert r.is_ok is False


# ═══════════════════════════════════════════════
# RateLimiter
# ═══════════════════════════════════════════════

class TestRateLimiter:
    """Tests for the RateLimiter class."""

    def test_default_qps(self) -> None:
        rl = RateLimiter()
        assert rl.interval == 1.0
        assert rl.jitter == 0.3

    def test_custom_qps(self) -> None:
        rl = RateLimiter(qps=5, jitter=0.1)
        assert rl.interval == 0.2
        assert rl.jitter == 0.1

    def test_zero_jitter(self) -> None:
        rl = RateLimiter(qps=10, jitter=0)
        assert rl.jitter == 0.0

    def test_qps_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="qps must be positive"):
            RateLimiter(qps=0)

    def test_qps_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="qps must be positive"):
            RateLimiter(qps=-1)

    def test_first_call_no_wait(self) -> None:
        rl = RateLimiter(qps=100, jitter=0)
        start = time.monotonic()
        rl.wait()
        elapsed = time.monotonic() - start
        # First call should be nearly instant (well under 0.01s).
        assert elapsed < 0.02, f"First call took {elapsed:.4f}s"

    def test_enforces_rate(self) -> None:
        rl = RateLimiter(qps=10, jitter=0)
        start = time.monotonic()
        for _ in range(5):
            rl.wait()
        elapsed = time.monotonic() - start
        # 5 calls at 0.1s interval = 0.4s minimum; allow 0.35s for timer slop.
        assert elapsed >= 0.35, f"Too fast: {elapsed:.3f}s"

    def test_jitter_adds_variability(self) -> None:
        rl = RateLimiter(qps=2, jitter=0.5)
        times: list[float] = []
        for _ in range(10):
            rl.wait()
            times.append(time.monotonic())

    def test_wait_when_elapsed_exceeds_interval(self) -> None:
        """Cover the branch where elapsed >= interval, giving sleep_for=0.0."""
        rl = RateLimiter(qps=100, jitter=0)
        rl.wait()
        assert rl._last_time > 0
        # Sleep long enough so elapsed > interval.
        time.sleep(0.1)
        start = time.monotonic()
        rl.wait()  # should be nearly instant (no enforced wait)
        elapsed = time.monotonic() - start
        assert elapsed < 0.02, f"Should be almost instant, got {elapsed:.4f}s"


# ═══════════════════════════════════════════════
# CookieManager
# ═══════════════════════════════════════════════

class TestCookieManager:
    """Tests for the CookieManager class."""

    def test_creates_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = os.path.join(td, "sub", "cookies")
            CookieManager(cookie_dir=d)
            assert os.path.isdir(d)

    def test_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cm = CookieManager(cookie_dir=td)
            cookies = [{"name": "session", "value": "abc123"}]
            path = cm.save("leetcode", cookies)
            assert path.exists()
            loaded = cm.load("leetcode")
            assert loaded == cookies

    def test_load_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cm = CookieManager(cookie_dir=td)
            assert cm.load("nonexistent") is None

    def test_load_broken_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cm = CookieManager(cookie_dir=td)
            path = cm._path("broken")
            path.write_text("not valid json", encoding="utf-8")
            assert cm.load("broken") is None

    def test_load_missing_cookies_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cm = CookieManager(cookie_dir=td)
            path = cm._path("nokey")
            path.write_text('{"platform":"nokey","saved_at":1.0}', encoding="utf-8")
            assert cm.load("nokey") is None

    def test_is_expired_true_for_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cm = CookieManager(cookie_dir=td)
            assert cm.is_expired("ghost") is True

    def test_is_expired_false_for_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cm = CookieManager(cookie_dir=td)
            cm.save("fresh", [{"name": "a"}])
            assert cm.is_expired("fresh") is False

    def test_is_expired_true_for_old(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cm = CookieManager(cookie_dir=td)
            cm.save("old", [{"name": "a"}])
            path = cm._path("old")
            payload = json.loads(path.read_text("utf-8"))
            payload["saved_at"] = time.time() - 31 * 86400  # 31 days ago
            path.write_text(json.dumps(payload), encoding="utf-8")
            assert cm.is_expired("old") is True

    def test_is_expired_broken_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cm = CookieManager(cookie_dir=td)
            path = cm._path("broken")
            path.write_text("{", encoding="utf-8")
            assert cm.is_expired("broken") is True


# ═══════════════════════════════════════════════
# RetryConfig
# ═══════════════════════════════════════════════

class TestRetryConfig:
    """Tests for the RetryConfig dataclass."""

    def test_defaults(self) -> None:
        cfg = RetryConfig()
        assert cfg.max_retries == 3
        assert cfg.base_delay == 1.0
        assert cfg.backoff_multiplier == 2.0
        assert cfg.max_delay == 30.0

    def test_custom(self) -> None:
        cfg = RetryConfig(max_retries=5, base_delay=2.0, backoff_multiplier=3.0, max_delay=60.0)
        assert cfg.max_retries == 5
        assert cfg.base_delay == 2.0
        assert cfg.backoff_multiplier == 3.0
        assert cfg.max_delay == 60.0


# ═══════════════════════════════════════════════
# CrawlerExecutor._is_retryable
# ═══════════════════════════════════════════════

class TestIsRetryable:
    """Tests for CrawlerExecutor._is_retryable static method."""

    @pytest.mark.parametrize("text", [
        "HTTP 429 Too Many Requests",
        "503 Service Unavailable",
        "connection timed out",
        "read timeout",
        "Connection reset by peer",
        "Connection refused",
        "Too Many Requests",
        "rate limit exceeded",
        "service unavailable",
        "temporarily unavailable",
        "DNS lookup failed",
        "network error",
        "RemoteDisconnected",
        "ProtocolError",
    ])
    def test_retryable(self, text: str) -> None:
        assert CrawlerExecutor._is_retryable(text) is True

    @pytest.mark.parametrize("text", [
        "404 Not Found",
        "500 Internal Server Error",
        "KeyError: 'foo'",
        "ValueError: invalid literal",
        "permission denied",
        "authentication failed",
    ])
    def test_not_retryable(self, text: str) -> None:
        assert CrawlerExecutor._is_retryable(text) is False

    def test_exception_object(self) -> None:
        assert CrawlerExecutor._is_retryable(TimeoutError("timed out")) is True
        assert CrawlerExecutor._is_retryable(ValueError("bad value")) is False


# ═══════════════════════════════════════════════
# Concrete crawler for testing BaseCrawler
# ═══════════════════════════════════════════════

class _TestCrawler(BaseCrawler):
    """Minimal concrete crawler for testing BaseCrawler."""

    PLATFORM = "test-platform"

    def fetch_user_profile(self, uid: str) -> CrawlResult:
        return CrawlResult(True, data={"uid": uid})

    def fetch_user_records(self, uid: str, since: str | None = None) -> CrawlResult:
        return CrawlResult(True, data={"uid": uid, "since": since})

    def fetch_problem(self, source_id: str) -> CrawlResult:
        return CrawlResult(True, data={"source_id": source_id})

    def fetch_problems_by_tag(self, tag: str, count: int = 50) -> CrawlResult:
        return CrawlResult(True, data={"tag": tag, "count": count})


# ═══════════════════════════════════════════════
# BaseCrawler
# ═══════════════════════════════════════════════

class TestBaseCrawler:
    """Tests for BaseCrawler (via _TestCrawler)."""

    def test_platform_required(self) -> None:
        """Instantiating abstract BaseCrawler is rejected by the ABC metaclass."""
        with pytest.raises(TypeError, match="abstract"):
            BaseCrawler()

    def test_default_qps(self) -> None:
        assert _TestCrawler._default_qps() == 1.0

    def test_data_dir_created(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=os.path.join(td, "raw"))
            assert crawler.data_dir.exists()

    def test_save_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            path = crawler.save_json({"hello": "world"}, "test.json")
            assert path.exists()
            data = json.loads(path.read_text("utf-8"))
            assert data == {"hello": "world"}

    def test_save_json_with_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            path = crawler.save_json([1, 2], "items.json", sub_dir="leetcode")
            assert path.parent.name == "leetcode"
            data = json.loads(path.read_text("utf-8"))
            assert data == [1, 2]

    def test_fetch_user_profile(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            result = crawler.fetch_user_profile("user123")
            assert result.success
            assert result.data == {"uid": "user123"}  # type: ignore[index]

    def test_fetch_user_records(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            result = crawler.fetch_user_records("user123")
            assert result.success
            assert result.data is not None
            assert result.data["uid"] == "user123"  # type: ignore[index]

    def test_fetch_problem(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            result = crawler.fetch_problem("two-sum")
            assert result.success
            assert result.data == {"source_id": "two-sum"}  # type: ignore[index]

    def test_fetch_problems_by_tag(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            result = crawler.fetch_problems_by_tag("dp", count=10)
            assert result.success
            assert result.data == {"tag": "dp", "count": 10}  # type: ignore[index]

    def test_close_no_browser(self) -> None:
        """close() should be safe even if browser was never launched."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            crawler.close()  # no-op, no exception


# ═══════════════════════════════════════════════
# CrawlerExecutor
# ═══════════════════════════════════════════════

class TestCrawlerExecutor:
    """Tests for the CrawlerExecutor class."""

    def test_execute_success(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            executor = CrawlerExecutor(crawler)
            result = executor.execute("fetch_problem", "abc")
            assert result.success
            assert result.data == {"source_id": "abc"}  # type: ignore[index]
            assert result.retry_count == 0

    def test_execute_unknown_method(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            executor = CrawlerExecutor(crawler)
            result = executor.execute("nonexistent_method")
            assert not result.success
            assert "not found" in (result.error or "")

    def test_retry_on_429_then_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            call_count = [0]

            def flaky_fetch(source_id: str) -> CrawlResult:
                call_count[0] += 1
                if call_count[0] < 3:
                    return CrawlResult(False, error="HTTP 429 Too Many Requests")
                return CrawlResult(True, data={"source_id": source_id})

            crawler.fetch_problem = flaky_fetch  # type: ignore[method-assign]
            executor = CrawlerExecutor(crawler)
            result = executor.execute("fetch_problem", "xyz")
            assert result.success
            assert call_count[0] == 3
            assert result.retry_count == 2

    def test_retry_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)

            def always_429(source_id: str) -> CrawlResult:
                return CrawlResult(False, error="HTTP 429 Too Many Requests")

            crawler.fetch_problem = always_429  # type: ignore[method-assign]
            executor = CrawlerExecutor(crawler, RetryConfig(max_retries=2, base_delay=0.01))
            result = executor.execute("fetch_problem", "xyz")
            assert not result.success
            assert result.retry_count == 2
            assert "429" in (result.error or "")

    def test_non_retryable_error_stops_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            call_count = [0]

            def permission_denied(source_id: str) -> CrawlResult:
                call_count[0] += 1
                return CrawlResult(False, error="permission denied")

            crawler.fetch_problem = permission_denied  # type: ignore[method-assign]
            executor = CrawlerExecutor(crawler, RetryConfig(max_retries=5, base_delay=0.01))
            result = executor.execute("fetch_problem", "xyz")
            assert not result.success
            assert call_count[0] == 1  # no retries

    def test_retry_on_exception(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            call_count = [0]

            def raises_timeout(source_id: str) -> CrawlResult:
                call_count[0] += 1
                if call_count[0] < 2:
                    raise TimeoutError("connection timed out")
                return CrawlResult(True, data={"source_id": source_id})

            crawler.fetch_problem = raises_timeout  # type: ignore[method-assign]
            executor = CrawlerExecutor(crawler, RetryConfig(max_retries=3, base_delay=0.01))
            result = executor.execute("fetch_problem", "abc")
            assert result.success
            assert call_count[0] == 2

    def test_non_crawlresult_return_wrapped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)

            def returns_dict(source_id: str) -> dict:  # type: ignore[override]
                return {"raw": source_id}

            crawler.fetch_problem = returns_dict  # type: ignore[method-assign]
            executor = CrawlerExecutor(crawler)
            result = executor.execute("fetch_problem", "hello")
            assert result.success
            assert result.data == {"raw": "hello"}


# ═══════════════════════════════════════════════
# DataImporter
# ═══════════════════════════════════════════════

class TestDataImporter:
    """Tests for the DataImporter class.

    Uses AsyncMock for the prisma client to avoid needing a real database.
    """

    @pytest.fixture
    def prisma_mock(self) -> MagicMock:
        mock = MagicMock()
        mock.problem = MagicMock()
        mock.problem.upsert = AsyncMock(return_value=None)
        mock.record = MagicMock()
        mock.record.upsert = AsyncMock(return_value=None)
        return mock

    # -- _read_json_files -------------------------------------------------

    def test_read_json_files_missing_dir(self) -> None:
        records = DataImporter._read_json_files(Path("/nonexistent/path"))
        assert records == []

    def test_read_json_files_single_dict(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "2025-06-13_abc.json").write_text(
                '{"id": "1", "title": "hello"}', encoding="utf-8"
            )
            records = DataImporter._read_json_files(d)
            assert records == [{"id": "1", "title": "hello"}]

    def test_read_json_files_list(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "items.json").write_text(
                '[{"id":"1"}, {"id":"2"}]', encoding="utf-8"
            )
            records = DataImporter._read_json_files(d)
            assert records == [{"id": "1"}, {"id": "2"}]

    def test_read_json_files_date_filter(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "2025-06-13_abc.json").write_text('{"id":"1"}', encoding="utf-8")
            (d / "2025-06-14_def.json").write_text('{"id":"2"}', encoding="utf-8")
            records = DataImporter._read_json_files(d, date="2025-06-13")
            assert records == [{"id": "1"}]

    def test_read_json_files_skips_broken(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "bad.json").write_text("not json", encoding="utf-8")
            (d / "good.json").write_text('{"ok": true}', encoding="utf-8")
            records = DataImporter._read_json_files(d)
            assert records == [{"ok": True}]

    # -- import_problems --------------------------------------------------

    @pytest.mark.asyncio
    async def test_import_problems_empty_dir(self, prisma_mock: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as td:
            importer = DataImporter(prisma_mock)
            importer.data_dir = Path(td)
            count = await importer.import_problems("leetcode")
            assert count == 0

    @pytest.mark.asyncio
    async def test_import_problems_upserts(self, prisma_mock: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as td:
            importer = DataImporter(prisma_mock)
            importer.data_dir = Path(td)
            problems_dir = importer._platform_dir("leetcode") / "problems"
            problems_dir.mkdir(parents=True)
            (problems_dir / "p1.json").write_text(
                '{"source_id":"two-sum","title":"Two Sum","difficulty":"easy","tags":["array"],"content":"..."}',
                encoding="utf-8",
            )
            count = await importer.import_problems("leetcode")
            assert count == 1
            prisma_mock.problem.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_import_problems_skips_missing_source_id(self, prisma_mock: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as td:
            importer = DataImporter(prisma_mock)
            importer.data_dir = Path(td)
            problems_dir = importer._platform_dir("cf") / "problems"
            problems_dir.mkdir(parents=True)
            (problems_dir / "bad.json").write_text(
                '{"title":"No ID"}', encoding="utf-8"
            )
            count = await importer.import_problems("cf")
            assert count == 0
            prisma_mock.problem.upsert.assert_not_awaited()

    # -- import_records ---------------------------------------------------

    @pytest.mark.asyncio
    async def test_import_records_empty_dir(self, prisma_mock: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as td:
            importer = DataImporter(prisma_mock)
            importer.data_dir = Path(td)
            count = await importer.import_records("leetcode")
            assert count == 0

    @pytest.mark.asyncio
    async def test_import_records_upserts(self, prisma_mock: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as td:
            importer = DataImporter(prisma_mock)
            importer.data_dir = Path(td)
            records_dir = importer._platform_dir("leetcode") / "records"
            records_dir.mkdir(parents=True)
            (records_dir / "r1.json").write_text(
                '{"id":"rec1","uid":"user1","problem_id":"two-sum","verdict":"AC","language":"cpp","timestamp":1234567890}',
                encoding="utf-8",
            )
            count = await importer.import_records("leetcode")
            assert count == 1
            prisma_mock.record.upsert.assert_awaited_once()

    # -- import_all -------------------------------------------------------

    @pytest.mark.asyncio
    async def test_import_all_no_dir(self, prisma_mock: MagicMock) -> None:
        importer = DataImporter(prisma_mock)
        importer.data_dir = Path("/nonexistent/abcdef")
        results = await importer.import_all()
        assert results == {}

    @pytest.mark.asyncio
    async def test_import_all_with_platforms(self, prisma_mock: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as td:
            importer = DataImporter(prisma_mock)
            importer.data_dir = Path(td)
            for plat in ("leetcode", "codeforces"):
                pdir = importer._platform_dir(plat) / "problems"
                pdir.mkdir(parents=True)
                (pdir / f"{plat}_p1.json").write_text(
                    f'{{"source_id":"{plat}-1","title":"Problem 1"}}',
                    encoding="utf-8",
                )
            results = await importer.import_all()
            assert results["leetcode"]["problems"] == 1
            assert results["codeforces"]["problems"] == 1
            assert prisma_mock.problem.upsert.await_count == 2


# ═══════════════════════════════════════════════
# Additional coverage tests
# ═══════════════════════════════════════════════

class _NoPlatformCrawler(BaseCrawler, ABC):
    """Concrete subclass that omits PLATFORM to trigger ValueError."""
    def fetch_user_profile(self, uid: str) -> CrawlResult:
        return CrawlResult(True)
    def fetch_user_records(self, uid: str, since: str | None = None) -> CrawlResult:
        return CrawlResult(True)
    def fetch_problem(self, source_id: str) -> CrawlResult:
        return CrawlResult(True)
    def fetch_problems_by_tag(self, tag: str, count: int = 50) -> CrawlResult:
        return CrawlResult(True)


class TestBaseCrawlerValueError:
    """Test that subclass without PLATFORM raises ValueError."""

    def test_missing_platform_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="PLATFORM"):
            _NoPlatformCrawler()


class TestBaseCrawlerCookiesAndBrowser:
    """Test BaseCrawler methods that interact with cookies and browser."""

    def test_init_loads_cookies_from_disk_and_applies(self) -> None:
        """__init__ loads cookies and calls _apply_cookies_to_session (lines 223-226)."""
        with tempfile.TemporaryDirectory() as td:
            saved_cookies = [{"name": "token", "value": "abc"}]
            with patch("crawlers.base.CookieManager") as MockCM:
                mock_cm = MockCM.return_value
                mock_cm.load.return_value = saved_cookies
                with patch.object(_TestCrawler, "_apply_cookies_to_session") as mock_apply:
                    crawler = _TestCrawler(data_dir=td)
                    mock_apply.assert_called_once_with(saved_cookies)

    def test_init_with_saved_cookies(self) -> None:
        """When cookies exist on disk, _apply_cookies_to_session is called."""
        with tempfile.TemporaryDirectory() as td:
            cookie_dir = os.path.join(td, "cookies")
            cm = CookieManager(cookie_dir=cookie_dir)
            cm.save("test-platform", [{"name": "token", "value": "x"}])

            crawler = _TestCrawler(data_dir=td)
            crawler._cookie_manager = cm
            # Replace _session to avoid DrissionPage property issues.
            mock_session = MagicMock()
            crawler._session = mock_session
            cookies = cm.load("test-platform")
            assert cookies is not None
            # Call _apply_cookies_to_session directly.
            crawler._apply_cookies_to_session(cookies)
            # Verify cookie was set.
            assert mock_session.set.cookies.call_count == 1

    def test_apply_cookies_exception_handled(self) -> None:
        """When setting cookies raises, it logs a warning instead of crashing."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            # Replace _session with a mock whose set.cookies raises.
            mock_session = MagicMock()
            mock_session.set.cookies.side_effect = TypeError("bad cookie")
            crawler._session = mock_session
            crawler._apply_cookies_to_session([{"name": "x"}])
            # Should not raise.

    def test_save_cookies_no_browser(self) -> None:
        """save_cookies with no browser launched saves empty list."""
        with tempfile.TemporaryDirectory() as td:
            cookie_dir = os.path.join(td, "cookies")
            cm = CookieManager(cookie_dir=cookie_dir)
            crawler = _TestCrawler(data_dir=td)
            crawler._cookie_manager = cm
            crawler.save_cookies()
            loaded = cm.load("test-platform")
            assert loaded == []

    def test_save_cookies_with_browser(self) -> None:
        """save_cookies with browser extracts and saves cookies."""
        with tempfile.TemporaryDirectory() as td:
            cookie_dir = os.path.join(td, "cookies")
            cm = CookieManager(cookie_dir=cookie_dir)
            crawler = _TestCrawler(data_dir=td)
            crawler._cookie_manager = cm
            fake_browser = MagicMock()
            fake_browser.cookies.return_value = [{"name": "session"}]
            crawler._browser = fake_browser
            crawler.save_cookies()
            loaded = cm.load("test-platform")
            assert loaded == [{"name": "session"}]

    def test_save_cookies_browser_exception(self) -> None:
        """save_cookies handles browser.cookies() raising."""
        with tempfile.TemporaryDirectory() as td:
            cookie_dir = os.path.join(td, "cookies")
            cm = CookieManager(cookie_dir=cookie_dir)
            crawler = _TestCrawler(data_dir=td)
            crawler._cookie_manager = cm
            fake_browser = MagicMock()
            fake_browser.cookies.side_effect = RuntimeError("boom")
            crawler._browser = fake_browser
            crawler.save_cookies()  # should not raise
            loaded = cm.load("test-platform")
            assert loaded == []  # fallback to empty

    def test_close_with_browser(self) -> None:
        """close() calls browser.quit() when browser is active."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            fake_browser = MagicMock()
            crawler._browser = fake_browser
            crawler.close()
            fake_browser.quit.assert_called_once()
            assert crawler._browser is None

    def test_close_browser_quit_raises(self) -> None:
        """close() handles browser.quit() raising an exception."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            fake_browser = MagicMock()
            fake_browser.quit.side_effect = RuntimeError("quit failed")
            crawler._browser = fake_browser
            crawler.close()  # should not raise
            assert crawler._browser is None

    def test_close_browser_quit_raises_and_already_none(self) -> None:
        """close() when browser.quit raises, still sets _browser to None."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            fake_browser = MagicMock()
            fake_browser.quit.side_effect = OSError("poof")
            crawler._browser = fake_browser
            crawler.close()
            assert crawler._browser is None

    def test_del_calls_close(self) -> None:
        """__del__ delegates to close()."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            fake_browser = MagicMock()
            crawler._browser = fake_browser
            # Trigger __del__ explicitly; this is a best-effort coverage call.
            crawler.__del__()  # type: ignore[call-arg]
            fake_browser.quit.assert_called_once()

    def test_del_when_close_raises(self) -> None:
        """__del__ survives if close() raises."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)

            def bad_close() -> None:
                raise RuntimeError("bad close")

            crawler.close = bad_close  # type: ignore[method-assign]
            # Should not raise.
            crawler.__del__()  # type: ignore[call-arg]

    def test_get_browser_lazy_init(self) -> None:
        """_get_browser creates a ChromiumPage on first call."""
        with tempfile.TemporaryDirectory() as td:
            with patch("crawlers.base.ChromiumPage") as MockCP:
                fake_browser = MagicMock()
                fake_browser.set = MagicMock()
                MockCP.return_value = fake_browser

                crawler = _TestCrawler(data_dir=td)
                assert crawler._browser is None
                result = crawler._get_browser()
                assert result is fake_browser
                assert crawler._browser is fake_browser
                MockCP.assert_called_once()

    def test_get_browser_returns_cached(self) -> None:
        """Second call to _get_browser returns the existing instance."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            fake = MagicMock()
            crawler._browser = fake
            assert crawler._get_browser() is fake


class TestBaseCrawlerHttpAndBrowser:
    """Test _http_request, _browser_request, and fetch_with_fallback with mocks."""

    def test_http_request_success_json(self) -> None:
        """_http_request returns successful CrawlResult with JSON data."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            fake_resp = MagicMock()
            fake_resp.status_code = 200
            fake_resp.json.return_value = {"key": "value"}
            with patch.object(crawler._session, "get", return_value=fake_resp):
                result = crawler._http_request("http://example.com")
            assert result.success
            assert result.data == {"key": "value"}
            assert result.source == "http"

    def test_http_request_success_non_json(self) -> None:
        """_http_request falls back to text when JSON parse fails."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            fake_resp = MagicMock()
            fake_resp.status_code = 200
            fake_resp.json.side_effect = ValueError("not json")
            fake_resp.text = "<html>ok</html>"
            with patch.object(crawler._session, "get", return_value=fake_resp):
                result = crawler._http_request("http://example.com")
            assert result.success
            assert result.data == {"text": "<html>ok</html>"}

    def test_http_request_429(self) -> None:
        """_http_request returns failure for 429 status."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            fake_resp = MagicMock()
            fake_resp.status_code = 429
            with patch.object(crawler._session, "get", return_value=fake_resp):
                result = crawler._http_request("http://example.com")
            assert not result.success
            assert "429" in (result.error or "")

    def test_http_request_500(self) -> None:
        """_http_request returns failure for 500 status."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            fake_resp = MagicMock()
            fake_resp.status_code = 500
            with patch.object(crawler._session, "get", return_value=fake_resp):
                result = crawler._http_request("http://example.com")
            assert not result.success
            assert result.error == "HTTP 500"

    def test_http_request_exception(self) -> None:
        """_http_request catches transport exceptions."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            with patch.object(crawler._session, "get", side_effect=ConnectionError("refused")):
                result = crawler._http_request("http://example.com")
            assert not result.success
            assert "refused" in (result.error or "")

    def test_browser_request_success(self) -> None:
        """_browser_request returns successful CrawlResult."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            fake_browser = MagicMock()
            fake_browser.html = "<html>data</html>"
            fake_browser.url = "http://example.com"
            crawler._browser = fake_browser
            with patch.object(crawler, "_get_browser", return_value=fake_browser):
                result = crawler._browser_request("http://example.com")
            assert result.success
            assert result.data == {"text": "<html>data</html>", "url": "http://example.com"}
            assert result.source == "browser"
            fake_browser.get.assert_called_once_with("http://example.com")

    def test_browser_request_exception(self) -> None:
        """_browser_request catches browser exceptions."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            fake_browser = MagicMock()
            fake_browser.get.side_effect = RuntimeError("crash")
            crawler._browser = fake_browser
            with patch.object(crawler, "_get_browser", return_value=fake_browser):
                result = crawler._browser_request("http://example.com")
            assert not result.success
            assert "crash" in (result.error or "")

    def test_fetch_with_fallback_http_success(self) -> None:
        """fetch_with_fallback returns HTTP result when successful."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            with patch.object(crawler, "_http_request", return_value=CrawlResult(True, data={"ok": 1}, source="http")):
                result = crawler.fetch_with_fallback("http://example.com")
            assert result.success
            assert result.source == "http"

    def test_fetch_with_fallback_http_fails_browser_succeeds(self) -> None:
        """fetch_with_fallback falls back to browser on HTTP failure."""
        with tempfile.TemporaryDirectory() as td:
            crawler = _TestCrawler(data_dir=td)
            with patch.object(crawler, "_http_request", return_value=CrawlResult(False, error="timeout", source="http")):
                with patch.object(crawler, "_browser_request", return_value=CrawlResult(True, data={"text": "fallback"}, source="browser")):
                    result = crawler.fetch_with_fallback("http://example.com")
            assert result.success
            assert result.source == "browser"


class TestDataImporterEdgeCases:
    """Additional DataImporter tests for exception handling and edge cases."""

    @pytest.fixture
    def prisma_mock(self) -> MagicMock:
        mock = MagicMock()
        mock.problem = MagicMock()
        mock.problem.upsert = AsyncMock(return_value=None)
        mock.record = MagicMock()
        mock.record.upsert = AsyncMock(return_value=None)
        return mock

    @pytest.mark.asyncio
    async def test_import_problems_upsert_raises(self, prisma_mock: MagicMock) -> None:
        """When prisma upsert raises, the error is logged and count is not incremented."""
        prisma_mock.problem.upsert.side_effect = RuntimeError("db offline")
        with tempfile.TemporaryDirectory() as td:
            importer = DataImporter(prisma_mock)
            importer.data_dir = Path(td)
            pdir = importer._platform_dir("leetcode") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "p1.json").write_text(
                '{"source_id":"a","title":"T"}', encoding="utf-8"
            )
            count = await importer.import_problems("leetcode")
            assert count == 0  # upsert failed, so no count

    @pytest.mark.asyncio
    async def test_import_records_upsert_raises(self, prisma_mock: MagicMock) -> None:
        """When prisma record upsert raises, the error is logged and count is not incremented."""
        prisma_mock.record.upsert.side_effect = RuntimeError("db offline")
        with tempfile.TemporaryDirectory() as td:
            importer = DataImporter(prisma_mock)
            importer.data_dir = Path(td)
            rdir = importer._platform_dir("cf") / "records"
            rdir.mkdir(parents=True)
            (rdir / "r1.json").write_text(
                '{"id":"r1","uid":"u","problem_id":"p","verdict":"AC","language":"py","timestamp":1}',
                encoding="utf-8",
            )
            count = await importer.import_records("cf")
            assert count == 0

    @pytest.mark.asyncio
    async def test_import_all_skips_non_dir(self, prisma_mock: MagicMock) -> None:
        """import_all skips entries that are not directories."""
        with tempfile.TemporaryDirectory() as td:
            importer = DataImporter(prisma_mock)
            importer.data_dir = Path(td)
            # Create a file (not dir) in data_dir.
            (Path(td) / "readme.txt").write_text("hello", encoding="utf-8")
            # Create a real platform dir with problems.
            pdir = importer._platform_dir("leetcode") / "problems"
            pdir.mkdir(parents=True)
            (pdir / "p1.json").write_text(
                '{"source_id":"lc-1","title":"Two Sum"}', encoding="utf-8"
            )
            results = await importer.import_all()
            assert "leetcode" in results
            assert "readme.txt" not in results
            assert results["leetcode"]["problems"] == 1

    @pytest.mark.asyncio
    async def test_read_json_files_oserror(self) -> None:
        """_read_json_files handles OSError when reading files."""
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            unreadable = d / "unreadable.json"
            unreadable.write_text('{"a":1}', encoding="utf-8")
            with patch("pathlib.Path.read_text", side_effect=OSError("perm")):
                records = DataImporter._read_json_files(d)
            assert records == []

    def test_data_importer_init(self) -> None:
        """DataImporter init stores prisma client and default data_dir."""
        mock = MagicMock()
        di = DataImporter(mock)
        assert di.prisma is mock
        assert di.data_dir == Path("data/raw")

    def test_platform_dir(self) -> None:
        """_platform_dir returns the correct sub-path."""
        di = DataImporter(MagicMock())
        assert di._platform_dir("leetcode") == Path("data/raw/leetcode")
