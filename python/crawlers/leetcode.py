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
    translatedTitle
    titleSlug
    content
    translatedContent
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
    metaData
  }
}
"""

_PROBLEMSET_QUERY = """
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList(
    categorySlug: $categorySlug
    limit: $limit
    skip: $skip
    filters: $filters
  ) {
    total
    questions {
      acRate
      difficulty
      freqBar
      frontendQuestionId
      isFavor
      paidOnly
      status
      title
      titleSlug
      topicTags { name id slug }
    }
  }
}
"""

_SOLUTIONS_QUERY = """
query questionSolutions($questionSlug: String!, $skip: Int!, $first: Int!) {
  questionSolutions(questionSlug: $questionSlug, skip: $skip, first: $first) {
    totalNum
    solutions {
      id
      title
      content
      post {
        author {
          username
        }
        voteCount
        creationDate
      }
    }
  }
}
"""

_OFFICIAL_SOLUTION_QUERY = """
query officialSolution($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    solution {
      content
      title
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
            self._session.post(
                self.GRAPHQL_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Origin": "https://leetcode.cn",
                    "Referer": "https://leetcode.cn/",
                },
            )

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

        slug = question.get("titleSlug") if isinstance(question, dict) else source_id
        if isinstance(question, dict):
            question["source_url"] = f"https://leetcode.cn/problems/{slug}/"
            # Prefer Chinese translations when available (leetcode.cn only)
            if question.get("translatedContent"):
                question["content"] = question["translatedContent"]
            if question.get("translatedTitle"):
                question["title"] = question["translatedTitle"]

            # ── Difficulty: convert string to numeric 1/2/3 ────
            import re as _re
            diff_str = str(question.get("difficulty", "")).strip().lower()
            diff_map = {"easy": 1, "medium": 2, "hard": 3}
            question["difficultyNormalized"] = diff_map.get(diff_str, 1)

            # ── LeetCode has no separate input/output format — the full
            # description (with examples, constraints, etc.) is self-contained
            # in the HTML `content` field.  The backend's `parseLeetCodeSamples`
            # extracts I/O pairs from the HTML; the rest becomes [描述].
            # Avoid false-positive extraction from example blocks like
            # "输入：s = \"42\"" which are sample data, not format specs.
            question["input_format"] = ""
            question["output_format"] = ""

            # ── Ensure hints is always a list in the returned data ──
            # hints from GraphQL is an array of strings; backend joins them.
            # Guard against both missing key and null/None value.
            if not question.get("hints"):
                question["hints"] = []

            # ── Parse samples ────────────────────────────────────
            # LeetCode's GraphQL `exampleTestcases` field contains INPUT
            # values only — it is NOT output data.  The actual expected
            # outputs are embedded in the HTML `content` field (inside
            # <pre> blocks with "Output:" / "输出：" labels).
            #
            # Instead of guessing outputs, we keep `sampleTestCase` as a
            # raw field and leave sample extraction to the backend's
            # `parseLeetCodeSamples()` which parses the real I/O pairs
            # from the HTML content.
            try:
                sample_test_case = (question.get("sampleTestCase") or "").strip()
                if sample_test_case:
                    question["sampleTestCase"] = sample_test_case
            except Exception:
                pass
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

    def fetch_solutions(
        self, source_id: str, first: int = 20
    ) -> CrawlResult:
        """Fetch community solutions and official solution for a problem.

        Queries two GraphQL endpoints:
        * ``questionSolutions(questionSlug, skip, first)`` for community solutions.
        * ``question(titleSlug){solution{content title}}`` for the official solution.

        Args:
            source_id: LeetCode problem title-slug (e.g. ``"two-sum"``).
            first: Maximum number of community solutions to fetch.

        Returns:
            CrawlResult with a list of solution dicts, each containing
            ``author``, ``content``, ``title``, ``vote_count``, and
            ``is_official`` fields.
        """
        solutions: list = []

        # ── Fetch community solutions ───────────────────────────
        comm_result = self._graphql(
            _SOLUTIONS_QUERY,
            variables={
                "questionSlug": source_id,
                "skip": 0,
                "first": first,
            },
        )
        if comm_result.success and comm_result.data:
            data = comm_result.data
            if isinstance(data, dict):
                qs = data.get("questionSolutions") or {}
                sol_list = qs.get("solutions", []) if isinstance(qs, dict) else []
                for s in sol_list:
                    if not isinstance(s, dict):
                        continue
                    post = s.get("post") or {}
                    author_info = (post.get("author") or {}) if isinstance(post, dict) else {}
                    solutions.append({
                        "author": author_info.get("username", "匿名"),
                        "title": s.get("title", ""),
                        "content": s.get("content", ""),
                        "vote_count": post.get("voteCount", 0) if isinstance(post, dict) else 0,
                        "is_official": False,
                        "solution_id": s.get("id", ""),
                    })

        # ── Fetch official solution ────────────────────────────
        off_result = self._graphql(
            _OFFICIAL_SOLUTION_QUERY,
            variables={"titleSlug": source_id},
        )
        if off_result.success and off_result.data:
            data = off_result.data
            if isinstance(data, dict):
                question = data.get("question") or {}
                off_sol = (question.get("solution") or {}) if isinstance(question, dict) else {}
                if isinstance(off_sol, dict) and off_sol.get("content"):
                    solutions.append({
                        "author": "LeetCode官方",
                        "title": off_sol.get("title", "官方题解"),
                        "content": off_sol.get("content", ""),
                        "vote_count": 0,
                        "is_official": True,
                        "solution_id": "official",
                    })

        if not solutions:
            return CrawlResult(
                success=False,
                error=f"No solutions found for problem '{source_id}'",
                source="http",
            )

        return CrawlResult(
            success=True,
            data=solutions,
            source="http",
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
    except (ImportError, RuntimeError):
        return CrawlResult(
            success=False,
            error="Prisma client not available. Install with: pip install prisma, then run: prisma generate",
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


def _save_result(crawler: LeetCodeCrawler, data, sub_dir: str, label: str) -> None:
    """Save fetched data to a timestamped JSON file under data/raw/{platform}/{sub_dir}/."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_label = str(label).replace("/", "_").replace("\\", "_")
    filename = f"{today}_{safe_label}.json"
    crawler.save_json(data, filename=filename, sub_dir=f"{crawler.PLATFORM}/{sub_dir}")


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
        choices=["fetch_problems", "fetch_detail", "fetch_user", "fetch_records", "fetch_solutions", "import"],
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
            if result.success and result.data:
                _save_result(crawler, result.data, "profiles", str(uid))

        elif action == "fetch_problems":
            tag = params.get("tags", "")
            count = int(params.get("count", 50))
            skip_ids = set(params.get("skip_ids", []))
            fetch_count = max(count + len(skip_ids), count * 3)
            result = executor.execute("fetch_problems_by_tag", str(tag), fetch_count)
            if result.success and result.data:
                new_items = [p for p in result.data if p.get('id') not in skip_ids and p.get('pid') not in skip_ids]
                new_items = new_items[:count]
                # Enrich with full detail (GraphQL query per problem)
                enriched = []
                for prob in new_items:
                    slug = prob.get('titleSlug') or prob.get('slug') or ''
                    if slug:
                        detail = executor.execute("fetch_problem", str(slug))
                        if detail and detail.success and detail.data:
                            enriched.append(dict(detail.data))
                        else:
                            enriched.append(prob)
                    else:
                        enriched.append(prob)
                result = CrawlResult(success=True, data=enriched, source=result.source)
                _save_result(crawler, result.data, "problems", str(tag) or "all")

        elif action == "fetch_records":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_records")
            result = executor.execute("fetch_user_records", str(uid))
            if result.success and result.data:
                _save_result(crawler, result.data, "records", str(uid))

        elif action == "fetch_detail":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_detail")
            result = executor.execute("fetch_problem", str(uid))
            if result.success and result.data:
                _save_result(crawler, result.data, "problems", str(uid))

        elif action == "fetch_solutions":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_solutions")
            count = int(params.get("count", 20))
            result = executor.execute("fetch_solutions", str(uid), count)
            if result.success and result.data:
                _save_result(crawler, result.data, "solutions", str(uid))

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
