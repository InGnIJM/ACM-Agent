"""
Codeforces platform crawler.

Uses the official Codeforces API (https://codeforces.com/api).
No browser fallback needed — CF has a stable, well-documented REST API.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Optional

from crawlers.base import BaseCrawler, CrawlResult, CrawlerExecutor, DataImporter

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# CodeforcesCrawler
# ──────────────────────────────────────────────


class CodeforcesCrawler(BaseCrawler):
    """Crawler for Codeforces (https://codeforces.com).

    All methods use ``_http_request`` exclusively — the official API
    is reliable and does not require browser-based fallback.
    """

    PLATFORM: str = "codeforces"

    # ── class constants ─────────────────────────────────────────

    API_URL: str = "https://codeforces.com/api"

    @staticmethod
    def _default_qps() -> float:
        """Codeforces allows ~5 requests per second in practice."""
        return 5.0

    # ── helpers ─────────────────────────────────────────────────

    def _api(self, method: str, **params: str) -> CrawlResult:
        """Call a Codeforces API method with query parameters.

        Args:
            method: API method path (e.g. ``"user.info"``).
            **params: Query-string parameters.

        Returns:
            CrawlResult with the API ``result`` field as data, or an
            error payload when ``status != "OK"``.
        """
        url = f"{self.API_URL}/{method}"
        # Build query string from non-None params.
        query_parts = [f"{k}={v}" for k, v in params.items() if v is not None]
        if query_parts:
            url += "?" + "&".join(query_parts)

        logger.debug("CF API call: %s", url)
        result = self._http_request(url)
        if not result.success:
            return result

        # Codeforces wraps every response in {"status": "...", "result": ...}.
        raw = result.data
        if isinstance(raw, dict):
            if raw.get("status") != "OK":
                return CrawlResult(
                    success=False,
                    error=raw.get("comment", "CF API returned non-OK status"),
                    source="http",
                    retry_count=result.retry_count,
                )
            return CrawlResult(
                success=True,
                data=raw.get("result"),
                source="http",
                retry_count=result.retry_count,
            )
        return result  # non-dict response is unexpected but forwarded

    # ── abstract method implementations ─────────────────────────

    def fetch_user_profile(self, uid: str) -> CrawlResult:
        """Fetch a Codeforces user's public profile.

        GET /api/user.info?handles={uid}

        Args:
            uid: Codeforces handle (case-sensitive).

        Returns:
            CrawlResult whose ``data`` is the user info dict (or None on failure).
        """
        result = self._api("user.info", handles=uid)
        if result.success and isinstance(result.data, list) and len(result.data) > 0:
            # CF returns a list of users; extract the first one.
            return CrawlResult(
                success=True,
                data=result.data[0],
                source="http",
                retry_count=result.retry_count,
            )
        if result.success and isinstance(result.data, dict):
            return result
        if result.success:
            return CrawlResult(
                success=False,
                error=f"User '{uid}' not found or empty response",
                source="http",
                retry_count=result.retry_count,
            )
        return result

    def fetch_user_records(
        self, uid: str, since: Optional[str] = None
    ) -> CrawlResult:
        """Fetch submissions for a Codeforces user.

        GET /api/user.status?handle={uid}&from=1&count=1000

        CF does not expose a server-side ``since`` filter so the
        parameter is accepted but ignored; callers should filter
        client-side if needed.

        Args:
            uid: Codeforces handle.
            since: *Ignored* — kept for interface compatibility.

        Returns:
            CrawlResult whose ``data`` is a list of submission dicts.
        """
        result = self._api(
            "user.status",
            handle=uid,
            **{"from": "1", "count": "1000"},
        )
        return result

    def fetch_problem(self, source_id: str) -> CrawlResult:
        """Look up a single problem by its CF contestId + index.

        This fetches the full problemset via GET /api/problemset.problems
        and filters client-side.  CF does not offer a single-problem
        endpoint.

        *source_id* is expected in the form ``"<contestId><index>"``
        (e.g. ``"1742E"``).  The function splits on the last digit
        boundary.

        Args:
            source_id: Problem identifier (e.g. ``"1742E"``).

        Returns:
            CrawlResult with the matched problem dict, or an error.
        """
        result = self._api("problemset.problems")
        if not result.success:
            return result

        raw = result.data
        if not isinstance(raw, dict):
            return CrawlResult(
                success=False,
                error="Unexpected problemset response format",
                source="http",
            )

        problems = raw.get("problems", [])
        # Parse "1742E" → contestId=1742, index="E"
        contest_id, index = self._parse_problem_id(source_id)
        for p in problems:
            if p.get("contestId") == contest_id and p.get("index") == index:
                return CrawlResult(
                    success=True,
                    data=p,
                    source="http",
                    retry_count=result.retry_count,
                )

        return CrawlResult(
            success=False,
            error=f"Problem '{source_id}' not found in problemset",
            source="http",
        )

    def fetch_problems_by_tag(
        self, tag: str, count: int = 50
    ) -> CrawlResult:
        """Fetch problems matching a given tag.

        GET /api/problemset.problems?tags={tag}

        Args:
            tag: CF tag (e.g. ``"dp"``, ``"greedy"``).
            count: Maximum number to return (default 50).

        Returns:
            CrawlResult with a list of up to *count* problem dicts.
        """
        result = self._api("problemset.problems", tags=tag)
        if not result.success:
            return result

        raw = result.data
        if not isinstance(raw, dict):
            return CrawlResult(
                success=False,
                error="Unexpected problemset response format",
                source="http",
            )

        problems = raw.get("problems", [])[:count]
        return CrawlResult(
            success=True,
            data=problems,
            source="http",
        )

    # ── internal helpers ────────────────────────────────────────

    @staticmethod
    def _parse_problem_id(source_id: str) -> tuple:
        """Split ``"1742E"`` → ``(1742, "E")``.

        Returns ``(0, source_id)`` if parsing fails.
        """
        import re

        m = re.match(r"^(\d+)([A-Z]\d*)$", source_id)
        if m:
            return int(m.group(1)), m.group(2)
        return 0, source_id


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
    """CLI entry point for the Codeforces crawler.

    Two modes are supported:

    * **NestJS mode** – ``--input`` receives a JSON string with all
      parameters (``action``, ``uid``, ``tags``, ``count``).
    * **CLI mode** – each parameter is supplied via its own argparse flag.

    Output is always a single JSON object printed to stdout.
    """
    parser = argparse.ArgumentParser(description="Codeforces crawler CLI")
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
                platform="codeforces",
            )
            sys.exit(1)
    else:
        if not args.action:
            _emit(
                success=False,
                error="Either --action or --input is required",
                platform="codeforces",
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
        _emit(success=False, error="Missing 'action' in parameters", platform="codeforces")
        sys.exit(1)

    # ── execute ────────────────────────────────────────────────
    crawler = CodeforcesCrawler()
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
    platform: str = "codeforces",
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
