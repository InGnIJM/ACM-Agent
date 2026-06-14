"""
NowCoder (牛客网) platform crawler.

NowCoder does not expose a public REST or GraphQL API.  All data is
obtained by fetching HTML pages and parsing them via ``fetch_with_fallback``
(HTTP first, then browser fallback).

HTML parsing is minimal and defensive: if the expected DOM structure
changes, methods return a failure ``CrawlResult`` instead of crashing.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from crawlers.base import BaseCrawler, CrawlResult

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# NowCoderCrawler
# ──────────────────────────────────────────────


class NowCoderCrawler(BaseCrawler):
    """Crawler for NowCoder (https://ac.nowcoder.com).

    Uses ``fetch_with_fallback`` for every endpoint; HTML responses are
    parsed with regex / ``json.loads``-in-script-tag extraction.

    If the HTML structure changes upstream these methods will degrade
    gracefully to failure rather than raising exceptions.
    """

    PLATFORM: str = "nowcoder"

    # ── class constants ─────────────────────────────────────────

    BASE_URL: str = "https://ac.nowcoder.com"

    @staticmethod
    def _default_qps() -> float:
        return 2.0

    # ── HTML extraction helpers ─────────────────────────────────

    @staticmethod
    def _extract_json_from_script(
        html: str, var_pattern: str
    ) -> Optional[Any]:
        """Extract a JSON value assigned to a JS variable in a ``<script>`` tag.

        Typical NowCoder pattern:

            <script>window.__INITIAL_STATE__ = {...};</script>

        Args:
            html: Full HTML page text.
            var_pattern: Regex pattern that captures the JSON payload in
                         group 1 (e.g. ``r'__INITIAL_STATE__\\s*=\\s*(\\{.*?\\});'``).

        Returns:
            Parsed Python object, or ``None`` on failure.
        """
        m = re.search(var_pattern, html, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to parse JSON from script tag: %s", exc)
            return None

    @staticmethod
    def _get_text_from_result(result: CrawlResult) -> Optional[str]:
        """Extract a plain-text string from a ``CrawlResult`` payload.

        Handles both ``{"text": "<html>..."}`` (browser source) and
        dict/list data (stringified).
        """
        data = result.data
        if isinstance(data, dict):
            return data.get("text") if "text" in data else json.dumps(data)
        if isinstance(data, list):
            return json.dumps(data)
        return str(data) if data else None

    # ── abstract method implementations ─────────────────────────

    def fetch_user_profile(self, uid: str) -> CrawlResult:
        """Fetch a NowCoder user's public profile page.

        GET https://ac.nowcoder.com/acm/contest/profile/{uid}

        The profile data is embedded as ``window.__INITIAL_STATE__``
        in the HTML.

        Args:
            uid: NowCoder user ID (numeric, e.g. ``"123456"``).

        Returns:
            CrawlResult with profile dict, or error.
        """
        url = f"{self.BASE_URL}/acm/contest/profile/{uid}"
        result = self.fetch_with_fallback(url)

        if not result.success:
            return result

        html = self._get_text_from_result(result)
        if not html:
            return CrawlResult(
                success=False,
                error="Empty response body",
                source=result.source,
            )

        # Attempt to extract window.__INITIAL_STATE__.
        extracted = self._extract_json_from_script(
            html,
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        )
        if extracted is None:
            # Fallback: try other script patterns.
            extracted = self._extract_json_from_script(
                html,
                r'window\.__NUXT__\s*=\s*(\{.*?\});',
            )

        if extracted is None:
            return CrawlResult(
                success=False,
                error="Could not extract profile data from page HTML",
                source=result.source,
            )

        # The profile is usually nested; try common paths.
        profile = None
        if isinstance(extracted, dict):
            profile = (
                extracted.get("profile")
                or extracted.get("userData")
                or extracted.get("userInfo")
                or extracted.get("state", {}).get("profile")
                or extracted
            )

        return CrawlResult(
            success=True,
            data=profile,
            source=result.source,
            retry_count=result.retry_count,
        )

    def fetch_user_records(
        self, uid: str, since: Optional[str] = None
    ) -> CrawlResult:
        """Fetch a user's AC submission list.

        GET https://ac.nowcoder.com/acm/contest/profile/{uid}/practice-coding

        The submission list is rendered server-side in the HTML table.

        Args:
            uid: NowCoder user ID.
            since: *Accepted but ignored* — the profile page includes
                   all submissions.

        Returns:
            CrawlResult with a list of parsed submission dicts.
        """
        url = f"{self.BASE_URL}/acm/contest/profile/{uid}/practice-coding"
        result = self.fetch_with_fallback(url)

        if not result.success:
            return result

        html = self._get_text_from_result(result)
        if not html:
            return CrawlResult(
                success=False,
                error="Empty response body",
                source=result.source,
            )

        # Try to extract records from embedded state.
        extracted = self._extract_json_from_script(
            html,
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        )
        if isinstance(extracted, dict):
            records = (
                extracted.get("records")
                or extracted.get("submissionList")
                or extracted.get("practiceList")
                or []
            )
            if records:
                return CrawlResult(
                    success=True,
                    data=records if isinstance(records, list) else [],
                    source=result.source,
                    retry_count=result.retry_count,
                )

        # Fallback: scrape the table rows.
        records = self._scrape_submission_table(html)
        return CrawlResult(
            success=True,
            data=records,
            source=result.source,
            retry_count=result.retry_count,
        )

    def fetch_problem(self, source_id: str) -> CrawlResult:
        """Fetch a single problem by its NowCoder problem ID.

        GET https://ac.nowcoder.com/acm/problem/{source_id}

        Args:
            source_id: NowCoder problem ID (numeric, e.g. ``"12345"``).

        Returns:
            CrawlResult with problem data.
        """
        url = f"{self.BASE_URL}/acm/problem/{source_id}"
        result = self.fetch_with_fallback(url)

        if not result.success:
            return result

        html = self._get_text_from_result(result)
        if not html:
            return CrawlResult(
                success=False,
                error="Empty response body",
                source=result.source,
            )

        # Extract __INITIAL_STATE__.
        extracted = self._extract_json_from_script(
            html,
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        )
        if isinstance(extracted, dict):
            problem = (
                extracted.get("problem")
                or extracted.get("problemData")
                or extracted.get("question")
                or extracted
            )
            return CrawlResult(
                success=True,
                data=problem,
                source=result.source,
                retry_count=result.retry_count,
            )

        return CrawlResult(
            success=False,
            error="Could not extract problem data from page HTML",
            source=result.source,
        )

    def fetch_problems_by_tag(
        self, tag: str, count: int = 50
    ) -> CrawlResult:
        """Fetch problems from the problem set filtered by tag.

        GET https://ac.nowcoder.com/acm/problem/list?tag={tag}

        Args:
            tag: NowCoder tag ID or tag name.
            count: Maximum problems to return.

        Returns:
            CrawlResult with a list of problem summary dicts.
        """
        url = f"{self.BASE_URL}/acm/problem/list?tag={tag}"
        result = self.fetch_with_fallback(url)

        if not result.success:
            return result

        html = self._get_text_from_result(result)
        if not html:
            return CrawlResult(
                success=False,
                error="Empty response body",
                source=result.source,
            )

        # Try embedded state first.
        extracted = self._extract_json_from_script(
            html,
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        )
        if isinstance(extracted, dict):
            problems = (
                extracted.get("problemList")
                or extracted.get("problems")
                or extracted.get("list")
                or []
            )
            if problems:
                return CrawlResult(
                    success=True,
                    data=problems[:count] if isinstance(problems, list) else [],
                    source=result.source,
                    retry_count=result.retry_count,
                )

        # Fallback: scrape problem links from the page.
        problems = self._scrape_problem_list(html, count)
        return CrawlResult(
            success=True,
            data=problems,
            source=result.source,
            retry_count=result.retry_count,
        )

    # ── HTML scraping fallback helpers ──────────────────────────

    @staticmethod
    def _scrape_submission_table(html: str) -> List[Dict[str, str]]:
        """Parse the practice-coding HTML table into a list of records.

        This is a best-effort scraper; if the table structure changes
        it will return an empty list (rather than crashing).
        """
        records: List[Dict[str, str]] = []

        # Look for a <table> with class containing "record" or "submission".
        table_match = re.search(
            r'<table[^>]*class="[^"]*(?:record|submission|table)[^"]*"[^>]*>(.*?)</table>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        if not table_match:
            table_match = re.search(
                r"<table[^>]*>(.*?)</table>",
                html,
                re.DOTALL | re.IGNORECASE,
            )

        if not table_match:
            return records

        table_html = table_match.group(1)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE)

        for row in rows:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL | re.IGNORECASE)
            # Clean HTML tags from cells.
            clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            if len(clean) >= 3:
                records.append(
                    {
                        "problem": clean[0],
                        "verdict": clean[1] if len(clean) > 1 else "",
                        "time": clean[2] if len(clean) > 2 else "",
                    }
                )

        return records

    @staticmethod
    def _scrape_problem_list(
        html: str, max_count: int = 50
    ) -> List[Dict[str, str]]:
        """Scrape problem links from the problem-list page.

        Returns a list of dicts with ``id``, ``title``, and ``url`` keys.
        """
        problems: List[Dict[str, str]] = []

        # Match <a> tags linking to /acm/problem/<id>
        link_pattern = re.compile(
            r'<a[^>]*href="(/acm/problem/(\d+))"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE,
        )

        seen: set = set()
        for m in link_pattern.finditer(html):
            problem_id = m.group(2)
            if problem_id in seen:
                continue
            seen.add(problem_id)

            title = re.sub(r"<[^>]+>", "", m.group(3)).strip()
            problems.append(
                {
                    "id": problem_id,
                    "title": title,
                    "url": f"{NowCoderCrawler.BASE_URL}{m.group(1)}",
                }
            )

            if len(problems) >= max_count:
                break

        return problems
