"""
Base crawler framework with rate limiting, cookie management, retry logic,
and data import capabilities.

Provides the abstract foundation for platform-specific crawlers
(LeetCode, Codeforces, AtCoder, Luogu, NowCoder, etc.).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from DrissionPage import ChromiumPage, SessionPage

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 1. CrawlResult
# ──────────────────────────────────────────────

@dataclass
class CrawlResult:
    """Unified result from any crawl operation (HTTP or browser).

    Attributes:
        success: Whether the request succeeded.
        data: Parsed response data (dict, list, or None).
        error: Error message when success is False.
        source: Which channel produced the result ("http" or "browser").
        retry_count: Number of retries attempted before this result.
    """

    success: bool
    data: Optional[Union[dict, list]] = None
    error: Optional[str] = None
    source: str = "http"
    retry_count: int = 0

    @property
    def is_ok(self) -> bool:
        return self.success and self.data is not None

    def __bool__(self) -> bool:
        return self.success


# ──────────────────────────────────────────────
# 2. RateLimiter
# ──────────────────────────────────────────────

class RateLimiter:
    """Token-bucket-style rate limiter with optional jitter.

    Usage::

        limiter = RateLimiter(qps=2, jitter=0.3)
        for url in urls:
            limiter.wait()
            fetch(url)
    """

    def __init__(self, qps: float = 1.0, jitter: float = 0.3) -> None:
        if qps <= 0:
            raise ValueError(f"qps must be positive, got {qps}")
        self.interval: float = 1.0 / qps
        self.jitter: float = float(jitter)
        self._last_time: float = 0.0

    def wait(self) -> None:
        """Block until the next permitted slot, then record the access time."""
        now = time.monotonic()
        elapsed = now - self._last_time

        if self._last_time == 0.0:
            # First call – no wait needed.
            sleep_for = 0.0
        elif elapsed < self.interval:
            sleep_for = self.interval - elapsed
        else:
            sleep_for = 0.0

        # Apply jitter: [0, jitter * interval]
        if self.jitter > 0:
            jitter_sec = random.uniform(0, self.jitter * self.interval)
            sleep_for += jitter_sec

        if sleep_for > 0:
            time.sleep(sleep_for)

        self._last_time = time.monotonic()


# ──────────────────────────────────────────────
# 3. CookieManager
# ──────────────────────────────────────────────

class CookieManager:
    """Persist and restore cookies per platform as JSON files.

    Directory layout::

        {cookie_dir}/
            leetcode.json
            codeforces.json
            ...

    Each JSON file contains the raw cookie list (list of dicts).
    """

    _EXPIRATION_DAYS = 30  # default TTL for a cookie file

    def __init__(self, cookie_dir: str = "data/cookies") -> None:
        self.cookie_dir = Path(cookie_dir)
        self.cookie_dir.mkdir(parents=True, exist_ok=True)

    # -- helpers -------------------------------------------------------

    def _path(self, platform: str) -> Path:
        return self.cookie_dir / f"{platform}.json"

    # -- public API ----------------------------------------------------

    def save(self, platform: str, cookies: List[Dict[str, Any]]) -> Path:
        """Persist *cookies* (list of cookie dicts) for the given *platform*.

        Returns the file path written.
        """
        payload: Dict[str, Any] = {
            "platform": platform,
            "cookies": cookies,
            "saved_at": time.time(),
        }
        path = self._path(platform)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Cookies saved for %s → %s", platform, path)
        return path

    def load(self, platform: str) -> Optional[List[Dict[str, Any]]]:
        """Load cookie list for *platform*, or None if missing/broken.

        Supports both CookieManager format ``{platform, cookies, saved_at}``
        and raw cookie array ``[{name, value, ...}, ...]``.
        """
        path = self._path(platform)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            # CookieManager format: { platform, cookies: [...], saved_at }
            if isinstance(payload, dict) and "cookies" in payload:
                return payload["cookies"]
            # Raw array format: [{name, value, ...}, ...]
            if isinstance(payload, list) and len(payload) > 0:
                return payload
            return None
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to parse cookie file %s: %s", path, exc)
            return None

    def is_expired(self, platform: str) -> bool:
        """Return True if the cookie file is older than the expiry threshold."""
        path = self._path(platform)
        if not path.exists():
            return True
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                saved_at: float = payload.get("saved_at", 0.0)
            elif isinstance(payload, list):
                saved_at: float = 0.0  # raw array has no timestamp
            else:
                return True
        except (json.JSONDecodeError, KeyError, TypeError):
            return True
        return (time.time() - saved_at) > (self._EXPIRATION_DAYS * 86400)


# ──────────────────────────────────────────────
# 4. BaseCrawler (Abstract)
# ──────────────────────────────────────────────

class BaseCrawler(ABC):
    """Abstract crawler providing HTTP (SessionPage) and browser (ChromiumPage)
    transport with automatic fallback, rate limiting, and JSON persistence.

    Subclasses MUST:
    - Set ``PLATFORM`` (e.g. ``"leetcode"``).
    - Implement the four abstract fetch methods.
    """

    # ── class-level ──────────────────────────────────────────────

    PLATFORM: str = ""

    # ── init ─────────────────────────────────────────────────────

    def __init__(
        self,
        data_dir: str = "data/raw",
        headless: bool = True,
        qps: Optional[float] = None,
    ) -> None:
        if not self.PLATFORM:
            raise ValueError(
                "Subclass must define PLATFORM class attribute "
                "(e.g. PLATFORM = 'leetcode')"
            )

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.headless = headless

        # HTTP session (always available, lightweight).
        self._session: SessionPage = SessionPage()
        # Set a realistic browser User-Agent to reduce bot-detection blocks
        try:
            self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        })
        except AttributeError:
            pass  # DrissionPage 4.x uses _headers internally

        # Browser instance – created lazily on first use.
        self._browser: Optional[ChromiumPage] = None

        # Rate limiter for this crawler instance.
        if qps is None:
            qps = self._default_qps()
        self._rate_limiter = RateLimiter(qps=qps)

        # Cookie manager.
        self._cookie_manager = CookieManager()

        # Load cookies into the session and browser if available.
        cookies = self._cookie_manager.load(self.PLATFORM)
        if cookies:
            self._apply_cookies_to_session(cookies)

    # ── overridable hooks ────────────────────────────────────────

    @staticmethod
    def _default_qps() -> float:
        """Return the default queries-per-second for this platform.

        Override in subclasses to match platform rate limits.
        """
        return 1.0

    # ── lazy browser ─────────────────────────────────────────────

    def _get_browser(self) -> ChromiumPage:
        """Return (and lazily create) the ChromiumPage instance.

        On first call the browser is launched and cookies are applied.
        """
        if self._browser is None:
            logger.info("Launching browser (headless=%s) for %s", self.headless, self.PLATFORM)
            self._browser = ChromiumPage()  # DrissionPage reads headless from config or args
            self._browser.set.cookies(
                self._cookie_manager.load(self.PLATFORM) or []
            )
        return self._browser

    # ── cookie helpers ───────────────────────────────────────────

    def _apply_cookies_to_session(
        self, cookies: List[Dict[str, Any]]
    ) -> None:
        """Set cookies on the HTTP session."""
        try:
            for c in cookies:
                self._session.set.cookies(c)
        except Exception as exc:
            logger.warning("Failed to apply cookies to session: %s", exc)

    def save_cookies(self) -> None:
        """Extract cookies from the browser (if launched) and persist them.

        If the browser was never launched only the session cookies are saved.
        """
        cookies: List[Dict[str, Any]] = []
        if self._browser is not None:
            try:
                cookies = self._browser.cookies()
            except Exception:
                pass
        self._cookie_manager.save(self.PLATFORM, cookies)

    # ── HTTP transport ───────────────────────────────────────────

    def _http_request(
        self, url: str, retry_count: int = 0, **kwargs: Any
    ) -> CrawlResult:
        """Perform an HTTP GET via SessionPage and return a CrawlResult.

        DrissionPage 4.x: ``SessionPage.get()`` returns ``bool``.
        The actual response object is stored in ``self._session.response``.
        """
        self._rate_limiter.wait()
        try:
            ok = self._session.get(url, **kwargs)
            resp = self._session.response
            if resp is None:
                return CrawlResult(
                    success=False,
                    error="No response (possible connection error)",
                    source="http",
                    retry_count=retry_count,
                )
            if resp.status_code == 429:
                return CrawlResult(
                    success=False,
                    error="HTTP 429 Too Many Requests",
                    source="http",
                    retry_count=retry_count,
                )
            if 400 <= resp.status_code < 600:
                return CrawlResult(
                    success=False,
                    error=f"HTTP {resp.status_code}",
                    source="http",
                    retry_count=retry_count,
                )
            # Try JSON first, fall back to HTML text
            try:
                data = resp.json()
            except (json.JSONDecodeError, ValueError):
                data = resp.text
            return CrawlResult(
                success=True,
                data=data,
                source="http",
                retry_count=retry_count,
            )
        except Exception as exc:
            return CrawlResult(
                success=False,
                error=str(exc),
                source="http",
                retry_count=retry_count,
            )

    # ── browser transport ────────────────────────────────────────

    def _browser_request(
        self, url: str, retry_count: int = 0
    ) -> CrawlResult:
        """Navigate the browser to *url* and return page text in a CrawlResult."""
        self._rate_limiter.wait()
        try:
            browser = self._get_browser()
            browser.get(url)
            # Small pause for JS-rendered content to settle.
            time.sleep(1)
            return CrawlResult(
                success=True,
                data={"text": browser.html, "url": browser.url},
                source="browser",
                retry_count=retry_count,
            )
        except Exception as exc:
            return CrawlResult(
                success=False,
                error=str(exc),
                source="browser",
                retry_count=retry_count,
            )

    # ── fallback: HTTP → browser ─────────────────────────────────

    def fetch_with_fallback(
        self, url: str, **kwargs: Any
    ) -> CrawlResult:
        """Try HTTP first; on failure fall back to the browser.

        Returns the first successful ``CrawlResult``.
        """
        result = self._http_request(url, **kwargs)
        if result.success:
            return result

        logger.info(
            "HTTP request failed (%s), falling back to browser for %s",
            result.error,
            url,
        )
        return self._browser_request(url)

    # ── persistence ──────────────────────────────────────────────

    def save_json(
        self,
        data: Union[dict, list],
        filename: str,
        sub_dir: str = "",
    ) -> Path:
        """Save *data* as JSON under ``data_dir / sub_dir / filename``.

        Directories are created automatically. Returns the written Path.
        """
        target_dir = self.data_dir / sub_dir if sub_dir else self.data_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        path = target_dir / filename
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.debug("Saved JSON → %s", path)
        return path

    # ── abstract methods ─────────────────────────────────────────

    @abstractmethod
    def fetch_user_profile(self, uid: str) -> CrawlResult:
        """Fetch a user's public profile."""
        ...

    @abstractmethod
    def fetch_user_records(
        self, uid: str, since: Optional[str] = None
    ) -> CrawlResult:
        """Fetch a user's submission / contest records."""
        ...

    @abstractmethod
    def fetch_problem(self, source_id: str) -> CrawlResult:
        """Fetch problem metadata by platform-native ID."""
        ...

    @abstractmethod
    def fetch_problems_by_tag(
        self, tag: str, count: int = 50
    ) -> CrawlResult:
        """Fetch up to *count* problems matching a given *tag*."""
        ...

    # ── cleanup ──────────────────────────────────────────────────

    def close(self) -> None:
        """Release browser resources if the browser was launched."""
        if self._browser is not None:
            try:
                self._browser.quit()
            except Exception:
                pass
            self._browser = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


# ──────────────────────────────────────────────
# 5. CrawlerExecutor – retry wrapper
# ──────────────────────────────────────────────

# Strings that, when found in an error message, mark the error as retryable.
_RETRYABLE_SUBSTRINGS: List[str] = [
    "429",
    "503",
    "timeout",
    "timed out",
    "connection reset",
    "connection refused",
    "too many requests",
    "rate limit",
    "service unavailable",
    "temporarily unavailable",
    "DNS",
    "network",
    "RemoteDisconnected",
    "ProtocolError",
]


@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0   # seconds
    backoff_multiplier: float = 2.0
    max_delay: float = 30.0   # seconds


class CrawlerExecutor:
    """Wrap a BaseCrawler method call with automatic retry on transient errors.

    Usage::

        crawler = LeetCodeCrawler()
        executor = CrawlerExecutor(crawler)
        result = executor.execute("fetch_problem", "two-sum")
    """

    def __init__(
        self,
        crawler: BaseCrawler,
        retry_config: Optional[RetryConfig] = None,
    ) -> None:
        self.crawler = crawler
        self.config = retry_config or RetryConfig()

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _is_retryable(error: Union[str, Exception]) -> bool:
        """Return True if the error string (or exception) indicates a
        transient / retryable condition.
        """
        text = str(error).lower()
        return any(token.lower() in text for token in _RETRYABLE_SUBSTRINGS)

    # ── public API ───────────────────────────────────────────────

    def execute(
        self, method_name: str, *args: Any, **kwargs: Any
    ) -> CrawlResult:
        """Call ``crawler.<method_name>(*args, **kwargs)`` with retry.

        On failure a new ``CrawlResult`` is built from the exception.
        Exponential backoff is applied between attempts.
        """
        method = getattr(self.crawler, method_name, None)
        if method is None:
            return CrawlResult(
                success=False,
                error=f"Method '{method_name}' not found on {type(self.crawler).__name__}",
            )

        last_error: Optional[str] = None

        for attempt in range(self.config.max_retries + 1):
            try:
                result: CrawlResult = method(*args, **kwargs)

                # Normalize: the method might return a CrawlResult or
                # a plain dict / list / bool (legacy compatibility).
                if not isinstance(result, CrawlResult):
                    result = CrawlResult(success=True, data=result, source="http")

                result.retry_count = attempt
                if result.success:
                    return result

                # The CrawlResult itself signals failure.
                last_error = result.error or "unknown error"
            except Exception as exc:
                last_error = str(exc)

            # Decide whether to retry.
            if attempt >= self.config.max_retries:
                break

            if not self._is_retryable(last_error or ""):
                # Non-retryable error – don't waste attempts.
                break

            # Exponential backoff with jitter.
            delay = min(
                self.config.base_delay
                * (self.config.backoff_multiplier ** attempt)
                + random.uniform(0, 0.5),
                self.config.max_delay,
            )
            logger.warning(
                "Retry %d/%d for %s.%s after %.1fs (%s)",
                attempt + 1,
                self.config.max_retries,
                type(self.crawler).__name__,
                method_name,
                delay,
                last_error,
            )
            time.sleep(delay)

        return CrawlResult(
            success=False,
            error=last_error or "max retries exceeded",
            source="http",
            retry_count=self.config.max_retries,
        )


# ──────────────────────────────────────────────
# 6. DataImporter
# ──────────────────────────────────────────────

class DataImporter:
    """Import crawled JSON files into the database via a Prisma client.

    Expected directory layout::

        data/raw/{platform}/problems/          # problem JSONs
        data/raw/{platform}/records/           # record JSONs

    Files are expected to be named with an ISO-8601 date prefix
    (e.g. ``2025-06-13_two-sum.json``) so that imports can be
    scoped to a specific date.

    Usage::

        from prisma import Prisma

        prisma = Prisma()
        await prisma.connect()
        importer = DataImporter(prisma)
        await importer.import_all("2025-06-13")
    """

    def __init__(self, prisma_client: Any) -> None:
        """*prisma_client* is the async Prisma client instance."""
        self.prisma = prisma_client
        self.data_dir = Path("data/raw")

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _read_json_files(
        directory: Path, date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Glob JSON files in *directory* (optionally filtered by *date* prefix).

        Returns a list of parsed records (each file may contain a single
        dict or a list of dicts).
        """
        records: List[Dict[str, Any]] = []
        if not directory.exists():
            logger.debug("Directory does not exist: %s", directory)
            return records

        pattern = f"{date}_*.json" if date else "*.json"
        for path in sorted(directory.glob(pattern)):
            # Skip bulk list files and progress snapshots — they don't have full detail
            if path.name.startswith("bulk_list_") or path.name.startswith("bulk_detail_progress_"):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping %s: %s", path, exc)
                continue

            if isinstance(payload, list):
                records.extend(payload)
            elif isinstance(payload, dict):
                records.append(payload)
        return records

    def _platform_dir(self, platform: str) -> Path:
        return self.data_dir / platform

    # ── import problems ──────────────────────────────────────────

    async def import_problems(
        self, platform: str, date: Optional[str] = None
    ) -> int:
        """Read problem JSONs for *platform* and upsert them via prisma.

        Returns the number of records upserted.
        """
        directory = self._platform_dir(platform) / "problems"
        records = self._read_json_files(directory, date)
        if not records:
            logger.info("No problem records to import for %s", platform)
            return 0

        count = 0
        for record in records:
            try:
                source_id = record.get("source_id") or record.get("id")
                # Codeforces: construct sourceId from contestId+index (e.g. "2236C")
                if not source_id and record.get("contestId") and record.get("index"):
                    source_id = f"{record['contestId']}{record['index']}"
                if not source_id:
                    logger.warning("Skipping problem record without source_id: %s", record)
                    continue
                await self.prisma.problem.upsert(
                    where={"platform_source_id": {
                        "platform": platform,
                        "source_id": str(source_id),
                    }},
                    data={
                        "create": {
                            "platform": platform,
                            "source_id": str(source_id),
                            "title": record.get("title", ""),
                            "difficulty": record.get("difficulty"),
                            "tags": record.get("tags", []),
                            "content": record.get("content", ""),
                            "raw_data": record,
                        },
                        "update": {
                            "title": record.get("title", ""),
                            "difficulty": record.get("difficulty"),
                            "tags": record.get("tags", []),
                            "content": record.get("content", ""),
                            "raw_data": record,
                            "deleted_at": None,  # restore soft-deleted records on re-import
                        },
                    },
                )
                count += 1
            except Exception as exc:
                logger.error(
                    "Failed to upsert problem %s on %s: %s",
                    record.get("source_id", record.get("id")),
                    platform,
                    exc,
                )

        logger.info("Imported %d problems for %s", count, platform)
        return count

    # ── import records ───────────────────────────────────────────

    async def import_records(
        self, platform: str, date: Optional[str] = None
    ) -> int:
        """Read record JSONs for *platform* and upsert them via prisma.

        Returns the number of records upserted.
        """
        directory = self._platform_dir(platform) / "records"
        records = self._read_json_files(directory, date)
        if not records:
            logger.info("No record records to import for %s", platform)
            return 0

        count = 0
        for record in records:
            try:
                platform_record_id = (
                    record.get("id")
                    or record.get("record_id")
                    or f"{record.get('uid', '')}_{record.get('timestamp', '')}"
                )
                await self.prisma.record.upsert(
                    where={
                        "platform_record_id": {
                            "platform": platform,
                            "record_id": str(platform_record_id),
                        }
                    },
                    data={
                        "create": {
                            "platform": platform,
                            "record_id": str(platform_record_id),
                            "uid": record.get("uid", ""),
                            "problem_id": record.get("problem_id"),
                            "verdict": record.get("verdict"),
                            "language": record.get("language"),
                            "timestamp": record.get("timestamp"),
                            "raw_data": record,
                        },
                        "update": {
                            "uid": record.get("uid", ""),
                            "problem_id": record.get("problem_id"),
                            "verdict": record.get("verdict"),
                            "language": record.get("language"),
                            "timestamp": record.get("timestamp"),
                            "raw_data": record,
                        },
                    },
                )
                count += 1
            except Exception as exc:
                logger.error(
                    "Failed to upsert record %s on %s: %s",
                    record.get("id", record.get("record_id")),
                    platform,
                    exc,
                )

        logger.info("Imported %d records for %s", count, platform)
        return count

    # ── import all ───────────────────────────────────────────────

    async def import_all(self, date: Optional[str] = None) -> Dict[str, Dict[str, int]]:
        """Import problems + records for every platform directory found
        under ``data/raw/``.

        Returns a dict like::

            {"leetcode": {"problems": 42, "records": 158}, ...}
        """
        results: Dict[str, Dict[str, int]] = {}
        if not self.data_dir.exists():
            logger.warning("Data directory does not exist: %s", self.data_dir)
            return results

        for platform_path in sorted(self.data_dir.iterdir()):
            if not platform_path.is_dir():
                continue
            platform = platform_path.name

            problem_count = await self.import_problems(platform, date)
            record_count = await self.import_records(platform, date)

            if problem_count or record_count:
                results[platform] = {
                    "problems": problem_count,
                    "records": record_count,
                }

        return results
