"""
LeetCode (力扣 CN) platform crawler.

Uses the LeetCode China GraphQL API (https://leetcode.cn/graphql).
All data is fetched via POST requests carrying GraphQL query documents.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from typing import Any, Dict, List, Optional

from crawlers.base import BaseCrawler, CrawlResult, CrawlerExecutor, DataImporter

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# GraphQL query templates
# ──────────────────────────────────────────────

_USER_PROFILE_QUERY = """
query getUserProfile($username: String!) {
  matchedUser(username: $username) {
    username
    profile {
      realName
      aboutMe
      userAvatar
      jobTitle
      company
      school
      websites
      countryName
      ranking
      reputation
      skillTags
    }
    submitStats {
      acSubmissionNum { difficulty count submissions }
      totalSubmissionNum { difficulty count submissions }
    }
    contributions {
      points
      questionCount
      testcaseCount
    }
  }
}
"""

_RECENT_AC_SUBMISSIONS_QUERY = """
query recentAcSubmissions($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    id
    title
    titleSlug
    timestamp
    lang
    statusDisplay
  }
}
"""

_PROBLEM_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    questionFrontendId
    title
    titleSlug
    content
    difficulty
    likes
    dislikes
    isLiked
    topicTags { name slug }
    codeSnippets { lang langSlug code }
    stats
    hints
    sampleTestCase
    exampleTestcases
  }
}
"""

_PROBLEMSET_QUERY = """
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList: questionList(
    categorySlug: $categorySlug
    limit: $limit
    skip: $skip
    filters: $filters
  ) {
    total: totalNum
    questions: data {
      acRate
      difficulty
      freqBar
      frontendQuestionId: questionFrontendId
      isFavor
      paidOnly: isPaidOnly
      status
      title
      titleSlug
      topicTags { name id slug }
    }
  }
}
"""

# ──────────────────────────────────────────────
# LeetCodeCrawler
# ──────────────────────────────────────────────


class LeetCodeCrawler(BaseCrawler):
    """Crawler for LeetCode China (https://leetcode.cn).

    All methods POST GraphQL queries to the GraphQL endpoint.  The
    base-class ``_http_request`` (GET-only) is not used; instead a
    dedicated ``_graphql`` helper issues POST requests through the
    same ``SessionPage``.
    """

    PLATFORM: str = "leetcode"

    # ── class constants ─────────────────────────────────────────

    GRAPHQL_URL: str = "https://leetcode.cn/graphql"

    @staticmethod
    def _default_qps() -> float:
        """LeetCode rate-limits aggressively; 1 QPS is safe."""
        return 1.0

    # ── GraphQL transport ───────────────────────────────────────

    def _graphql(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
    ) -> CrawlResult:
        """POST a GraphQL query and return the ``data`` envelope.

        Args:
            query: GraphQL query document.
            variables: Optional variables dict.
            retry_count: Retry counter (set by callers / executor).

        Returns:
            CrawlResult with ``data.data`` on success.
        """
        self._rate_limiter.wait()
        payload = {"query": query, "variables": variables or {}}

        try:
            resp = self._session.post(
                self.GRAPHQL_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Origin": "https://leetcode.cn",
                    "Referer": "https://leetcode.cn/",
                },
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

            try:
                body = resp.json()
            except (json.JSONDecodeError, ValueError):
                return CrawlResult(
                    success=False,
                    error="GraphQL response is not valid JSON",
                    source="http",
                    retry_count=retry_count,
                )

            # GraphQL errors are reported alongside data (status 200).
            errors = body.get("errors")
            data = body.get("data")

            if errors:
                # If there is no data at all, this is a hard failure.
                if data is None:
                    err_msgs = "; ".join(
                        e.get("message", str(e)) for e in errors
                    )
                    return CrawlResult(
                        success=False,
                        error=f"GraphQL errors: {err_msgs}",
                        source="http",
                        retry_count=retry_count,
                    )

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

    # ── abstract method implementations ─────────────────────────

    def fetch_user_profile(self, uid: str) -> CrawlResult:
        """Fetch a LeetCode user's profile + submit stats.

        POST graphql ``matchedUser(username)``.

        Args:
            uid: LeetCode username.

        Returns:
            CrawlResult with ``data.matchedUser``.
        """
        result = self._graphql(
            _USER_PROFILE_QUERY,
            variables={"username": uid},
        )
        if not result.success or result.data is None:
            return result

        matched = result.data.get("matchedUser") if isinstance(result.data, dict) else None
        if matched is None:
            return CrawlResult(
                success=False,
                error=f"User '{uid}' not found on LeetCode CN",
                source="http",
            )

        return CrawlResult(
            success=True,
            data=matched,
            source="http",
            retry_count=result.retry_count,
        )

    def fetch_user_records(
        self, uid: str, since: Optional[str] = None
    ) -> CrawlResult:
        """Fetch a user's recent accepted submissions.

        POST graphql ``recentAcSubmissionList``.

        Args:
            uid: LeetCode username.
            since: *Not used by the GraphQL API* — kept for interface
                   compatibility. The endpoint returns recent AC
                   submissions only (limited to 20 by default).

        Returns:
            CrawlResult with a list of recent AC submission dicts.
        """
        result = self._graphql(
            _RECENT_AC_SUBMISSIONS_QUERY,
            variables={"username": uid, "limit": 20},
        )
        if not result.success or result.data is None:
            return result

        data = result.data
        submissions = (
            data.get("recentAcSubmissionList", [])
            if isinstance(data, dict)
            else []
        )

        return CrawlResult(
            success=True,
            data=submissions,
            source="http",
            retry_count=result.retry_count,
        )

    def fetch_problem(self, source_id: str) -> CrawlResult:
        """Fetch a single problem by title slug.

        POST graphql ``question(titleSlug)``.

        Args:
            source_id: LeetCode problem title-slug
                       (e.g. ``"two-sum"``).

        Returns:
            CrawlResult with the ``question`` object.
        """
        result = self._graphql(
            _PROBLEM_QUERY,
            variables={"titleSlug": source_id},
        )
        if not result.success or result.data is None:
            return result

        question = (
            result.data.get("question")
            if isinstance(result.data, dict)
            else None
        )
        if question is None:
            return CrawlResult(
                success=False,
                error=f"Problem '{source_id}' not found on LeetCode CN",
                source="http",
            )

        return CrawlResult(
            success=True,
            data=question,
            source="http",
            retry_count=result.retry_count,
        )

    def fetch_problems_by_tag(
        self, tag: str, count: int = 50
    ) -> CrawlResult:
        """Fetch problems filtered by topic tag.

        POST graphql ``problemsetQuestionList`` with a tag filter.

        Args:
            tag: LeetCode topic tag slug (e.g. ``"array"``,
                 ``"dynamic-programming"``).
            count: Maximum number of problems to return.

        Returns:
            CrawlResult with a list of problem summary dicts.
        """
        variables: Dict[str, Any] = {
            "categorySlug": "",
            "limit": min(count, 100),  # LC caps at 100 per page
            "skip": 0,
            "filters": {"tags": [tag]},
        }

        result = self._graphql(_PROBLEMSET_QUERY, variables=variables)
        if not result.success or result.data is None:
            return result

        data = result.data
        if not isinstance(data, dict):
            return CrawlResult(
                success=False,
                error="Unexpected problemset response format",
                source="http",
            )

        pql = data.get("problemsetQuestionList", {})
        questions = pql.get("questions", []) if isinstance(pql, dict) else []

        return CrawlResult(
            success=True,
            data=questions[:count],
            source="http",
            retry_count=result.retry_count,
        )


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────


def _run_import(platform: str) -> CrawlResult:
    """Run DataImporter.import_all() for the given platform.

    Returns:
        CrawlResult wrapping the import results.
    """
    try:
        from prisma import Prisma  # type: ignore[import-untyped]
    except ImportError:
        return CrawlResult(
            success=False,
            error="Prisma client not installed. Install with: pip install prisma",
        )

    async def _import() -> CrawlResult:
        prisma = Prisma()
        await prisma.connect()
        try:
            importer = DataImporter(prisma)
            results = await importer.import_all()
            return CrawlResult(success=True, data=results)
        finally:
            await prisma.disconnect()

    try:
        return asyncio.run(_import())
    except Exception as exc:
        return CrawlResult(success=False, error=str(exc))


def main(argv: Optional[list] = None) -> None:
    """CLI entry point for the LeetCode crawler.

    Two modes are supported:

    * **NestJS mode** – ``--input`` receives a JSON string with all
      parameters (``action``, ``uid``, ``tags``, ``count``).
    * **CLI mode** – each parameter is supplied via its own argparse flag.

    Output is always a single JSON object printed to stdout.
    """
    parser = argparse.ArgumentParser(description="LeetCode crawler CLI")
    parser.add_argument(
        "--action",
        choices=["fetch_problems", "fetch_user", "fetch_records", "import"],
        default=None,
        help="Crawl action to execute",
    )
    parser.add_argument("--uid", default=None, help="User ID / handle")
    parser.add_argument("--tags", default=None, help="Tag for filtering problems")
    parser.add_argument("--count", type=int, default=50, help="Max items to fetch")
    parser.add_argument(
        "--input",
        default=None,
        help="JSON input string containing all parameters (NestJS mode)",
    )
    args = parser.parse_args(argv)

    # ── determine parameter source ─────────────────────────────
    if args.input:
        try:
            params: dict = json.loads(args.input)
        except json.JSONDecodeError as exc:
            _emit(
                success=False,
                error=f"Invalid JSON input: {exc}",
                platform="leetcode",
            )
            sys.exit(1)
    else:
        if not args.action:
            _emit(
                success=False,
                error="Either --action or --input is required",
                platform="leetcode",
            )
            sys.exit(1)
        params = {
            "action": args.action,
            "uid": args.uid,
            "tags": args.tags,
            "count": args.count,
        }

    action: str = params.get("action", "")
    if not action:
        _emit(success=False, error="Missing 'action' in parameters", platform="leetcode")
        sys.exit(1)

    # ── execute ────────────────────────────────────────────────
    crawler = LeetCodeCrawler()
    executor = CrawlerExecutor(crawler)

    try:
        if action == "fetch_user":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_user")
            result = executor.execute("fetch_user_profile", str(uid))

        elif action == "fetch_problems":
            tag = params.get("tags", "")
            count = int(params.get("count", 50))
            result = executor.execute("fetch_problems_by_tag", str(tag), count)

        elif action == "fetch_records":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_records")
            result = executor.execute("fetch_user_records", str(uid))

        elif action == "import":
            result = _run_import(crawler.PLATFORM)

        else:
            result = CrawlResult(success=False, error=f"Unknown action: {action}")

        _emit(
            success=result.success,
            data=result.data,
            error=result.error,
            platform=crawler.PLATFORM,
        )
    except Exception as exc:
        _emit(success=False, error=str(exc), platform=crawler.PLATFORM)
        sys.exit(1)
    finally:
        crawler.close()


def _emit(
    success: bool,
    platform: str = "leetcode",
    data: object = None,
    error: Optional[str] = None,
) -> None:
    """Print a JSON result line to stdout."""
    payload = {
        "success": success,
        "data": data,
        "error": error,
        "platform": platform,
    }
    print(json.dumps(payload, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
