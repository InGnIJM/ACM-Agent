"""
AtCoder platform crawler.

Uses the kenkoooo.com unofficial AtCoder API for submission history
and problem models.  For user profiles the official AtCoder site is
scraped via ``fetch_with_fallback`` (the kenkoooo API does not expose
user metadata).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from crawlers.base import BaseCrawler, CrawlResult

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# AtCoderCrawler
# ──────────────────────────────────────────────


class AtCoderCrawler(BaseCrawler):
    """Crawler for AtCoder (https://atcoder.jp).

    Submission records and problem metadata come from the
    `kenkoooo <https://kenkoooo.com/atcoder>`_ API.  User profiles
    are fetched from the official AtCoder site.
    """

    PLATFORM: str = "atcoder"

    # ── class constants ─────────────────────────────────────────

    KENKOO_API: str = "https://kenkoooo.com/atcoder"
    ATCODER_URL: str = "https://atcoder.jp"

    @staticmethod
    def _default_qps() -> float:
        return 2.0

    # ── kenkoooo API helper ─────────────────────────────────────

    def _kenkoo_request(self, path: str, **params: str) -> CrawlResult:
        """GET a kenkoooo API endpoint with query parameters.

        Args:
            path: API path relative to ``KENKOO_API``
                  (e.g. ``"/atcoder-api/v3/user/submissions"``).
            **params: Query-string parameters.

        Returns:
            CrawlResult.
        """
        url = f"{self.KENKOO_API}{path}"
        if params:
            qs = "&".join(
                f"{k}={v}" for k, v in params.items() if v is not None
            )
            url += f"?{qs}"

        logger.debug("Kenkoo GET: %s", url)
        return self._http_request(url)

    # ── abstract method implementations ─────────────────────────

    def fetch_user_profile(self, uid: str) -> CrawlResult:
        """Fetch an AtCoder user's profile from the official site.

        GET https://atcoder.jp/users/{uid}

        The kenkoooo API does not expose user metadata (rating history
        is available but not profile fields).  This method uses
        ``fetch_with_fallback`` to obtain the user page and extracts
        structured data from it.

        Args:
            uid: AtCoder user ID (case-sensitive).

        Returns:
            CrawlResult with profile data.
        """
        url = f"{self.ATCODER_URL}/users/{uid}"
        result = self.fetch_with_fallback(url)

        if not result.success:
            return result

        # Extract HTML text from the result.
        data = result.data
        if isinstance(data, dict) and "text" in data:
            html: str = data["text"]
        elif isinstance(data, str):
            html = data
        else:
            return CrawlResult(
                success=False,
                error="Unexpected response format from AtCoder profile page",
                source=result.source,
            )

        import re

        profile: Dict[str, object] = {"user_id": uid}

        # Rating
        rating_match = re.search(
            r'<span[^>]*class="[^"]*user-red[^"]*"[^>]*>(\d+)</span>', html
        ) or re.search(r'<span[^>]*class="[^"]*bold[^"]*"[^>]*>(\d+)</span>', html)
        if rating_match:
            profile["rating"] = int(rating_match.group(1))

        # Highest rating
        highest_match = re.search(r"Highest Rating[：:]\s*(\d+)", html)
        if highest_match:
            profile["highest_rating"] = int(highest_match.group(1))

        # Affiliation (所属)
        aff_match = re.search(r'<th[^>]*>Affiliation</th>\s*<td[^>]*>(.*?)</td>', html, re.DOTALL)
        if aff_match:
            profile["affiliation"] = aff_match.group(1).strip()

        # Country / region
        country_match = re.search(r'<th[^>]*>Country/Region</th>\s*<td[^>]*>(.*?)</td>', html, re.DOTALL)
        if country_match:
            profile["country"] = country_match.group(1).strip()

        # Rank (class)
        rank_match = re.search(r'<span[^>]*class="[^"]*user-(blue|orange|red|yellow|cyan|green|brown|gray|unrated)[^"]*"', html)
        if rank_match:
            profile["rank"] = rank_match.group(1)

        # Number of contests participated
        contests_match = re.search(r'<td[^>]*>(\d+)</td>\s*<td[^>]*class="[^"]*text-center[^"]*"[^>]*>\s*Contests', html, re.DOTALL | re.IGNORECASE)
        if contests_match:
            profile["contests_participated"] = int(contests_match.group(1))

        return CrawlResult(
            success=True,
            data=profile,
            source=result.source,
            retry_count=result.retry_count,
        )

    def fetch_user_records(
        self, uid: str, since: Optional[str] = None
    ) -> CrawlResult:
        """Fetch submission history via kenkoooo API.

        GET /atcoder-api/v3/user/submissions?user={uid}&from_second={since}

        Args:
            uid: AtCoder user ID.
            since: Unix timestamp (seconds) to filter submissions from.
                   If not provided, defaults to 0 (all submissions).

        Returns:
            CrawlResult whose ``data`` is a list of submission dicts.
        """
        from_second = since if since else "0"
        result = self._kenkoo_request(
            "/atcoder-api/v3/user/submissions",
            user=uid,
            from_second=from_second,
        )
        return result

    def fetch_problem(self, source_id: str) -> CrawlResult:
        """Fetch a single problem by its AtCoder problem ID.

        GET /atcoder-api/v3/problem/models (full list, filtered client-side).

        The kenkoooo API does not provide a single-problem endpoint,
        so the full problem list is fetched and filtered.

        Args:
            source_id: AtCoder problem ID
                       (e.g. ``"abc174_a"``, ``"arc108_c"``).

        Returns:
            CrawlResult with the matched problem dict.
        """
        result = self._kenkoo_request("/atcoder-api/v3/problem/models")
        if not result.success:
            return result

        problems = result.data
        if not isinstance(problems, list):
            return CrawlResult(
                success=False,
                error="Unexpected problem models response format",
                source="http",
            )

        # The kenkoooo problem "id" is the AtCoder problem ID.
        for p in problems:
            if isinstance(p, dict) and p.get("id") == source_id:
                return CrawlResult(
                    success=True,
                    data=p,
                    source="http",
                    retry_count=result.retry_count,
                )

        return CrawlResult(
            success=False,
            error=f"Problem '{source_id}' not found",
            source="http",
        )

    def fetch_problems_by_tag(
        self, tag: str, count: int = 50
    ) -> CrawlResult:
        """Fetch problems filtered by contest tag.

        GET /atcoder-api/v3/problem/models (full list, filtered client-side).

        The kenkoooo problem model includes a ``contest_id`` field.
        This method treats *tag* as a contest ID prefix filter.
        For example, ``tag="abc"`` returns problems from ABC contests.

        Args:
            tag: Contest ID prefix to filter by
                 (e.g. ``"abc"``, ``"arc"``, ``"agc"``).
            count: Maximum problems to return.

        Returns:
            CrawlResult with a list of matching problem dicts.
        """
        result = self._kenkoo_request("/atcoder-api/v3/problem/models")
        if not result.success:
            return result

        problems = result.data
        if not isinstance(problems, list):
            return CrawlResult(
                success=False,
                error="Unexpected problem models response format",
                source="http",
            )

        matching: List[dict] = []
        for p in problems:
            if not isinstance(p, dict):
                continue
            contest_id = p.get("contest_id", "")
            if isinstance(contest_id, str) and contest_id.lower().startswith(
                tag.lower()
            ):
                matching.append(p)
                if len(matching) >= count:
                    break

        return CrawlResult(
            success=True,
            data=matching,
            source="http",
        )
