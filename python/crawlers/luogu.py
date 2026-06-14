"""
Luogu (洛谷) platform crawler.

Uses Luogu's ``_contentOnly=1`` query parameter to obtain structured
JSON responses instead of full HTML pages.  No browser fallback is
required under normal circumstances.
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
# LuoguCrawler
# ──────────────────────────────────────────────


class LuoguCrawler(BaseCrawler):
    """Crawler for Luogu (https://www.luogu.com.cn).

    Appends ``?_contentOnly=1`` to every request so the server
    returns JSON instead of rendered HTML.
    """

    PLATFORM: str = "luogu"

    # ── class constants ─────────────────────────────────────────

    BASE_URL: str = "https://www.luogu.com.cn"

    @staticmethod
    def _default_qps() -> float:
        """Luogu rate-limits to roughly 2 requests/second."""
        return 2.0

    # ── helpers ─────────────────────────────────────────────────

    def _get_json(self, path: str, **params: str) -> CrawlResult:
        """GET *path* with ``_contentOnly=1`` appended.

        Returns the ``currentData`` field on success, or the raw
        response if the envelope is missing.
        """
        # Merge _contentOnly with any additional params.
        all_params = {"_contentOnly": "1", **params}
        qs = "&".join(f"{k}={v}" for k, v in all_params.items())
        url = f"{self.BASE_URL}{path}?{qs}"

        logger.debug("Luogu GET: %s", url)
        result = self._http_request(url)
        if not result.success:
            return result

        raw = result.data
        if isinstance(raw, dict):
            code = raw.get("code")
            if code is not None and code != 200:
                return CrawlResult(
                    success=False,
                    error=raw.get("currentTemplate", f"Luogu API returned code {code}"),
                    source="http",
                    retry_count=result.retry_count,
                )
            # Unwrap the payload.
            inner = raw.get("currentData")
            if inner is not None:
                return CrawlResult(
                    success=True,
                    data=inner,
                    source="http",
                    retry_count=result.retry_count,
                )
            # No currentData – return the whole envelope.
            return CrawlResult(
                success=True,
                data=raw,
                source="http",
                retry_count=result.retry_count,
            )
        return result

    # ── abstract method implementations ─────────────────────────

    def fetch_user_profile(self, uid: str) -> CrawlResult:
        """Fetch a Luogu user's public profile.

        GET /user/{uid}?_contentOnly=1

        Args:
            uid: Luogu user ID (numeric string, e.g. ``"1001"``).

        Returns:
            CrawlResult with user profile data.
        """
        result = self._get_json(f"/user/{uid}")
        if not result.success:
            return result

        data = result.data
        if isinstance(data, dict) and "user" in data:
            return CrawlResult(
                success=True,
                data=data["user"],
                source="http",
                retry_count=result.retry_count,
            )
        return result

    def fetch_user_records(
        self, uid: str, since: Optional[str] = None
    ) -> CrawlResult:
        """Fetch submission records for a Luogu user (paginated).

        GET /record/list?user={uid}&page=1&_contentOnly=1

        Pages through up to 5 pages (configurable via ``_max_pages``)
        to collect all recent records.  The ``since`` parameter is
        accepted for interface compatibility but client-side filtering
        is recommended.

        Args:
            uid: Luogu user ID.
            since: *Optional* timestamp for filtering (client-side).

        Returns:
            CrawlResult whose ``data`` is a list of record dicts.
        """
        all_records: list = []
        max_pages = 5

        for page in range(1, max_pages + 1):
            path = f"/record/list"
            result = self._get_json(path, user=uid, page=str(page))
            if not result.success:
                if page == 1:
                    return result
                # Later page failures are non-fatal.
                logger.warning(
                    "Luogu records page %d failed: %s", page, result.error
                )
                break

            data = result.data
            if not isinstance(data, dict):
                break

            records = data.get("records", {}).get("result", [])
            if not records:
                break  # No more records.

            all_records.extend(records)

            # If the server signals there are no more pages, stop.
            total_pages = (
                data.get("records", {}).get("count", 0)
                if isinstance(data.get("records"), dict)
                else 0
            )
            if page >= total_pages:
                break

        return CrawlResult(
            success=True,
            data=all_records,
            source="http",
        )

    def fetch_problem(self, source_id: str) -> CrawlResult:
        """Fetch a single problem's metadata.

        Uses browser mode to extract embedded JSON from the rendered page.

        Args:
            source_id: Luogu problem ID (e.g. ``"P1001"``).

        Returns:
            CrawlResult with problem data.
        """
        url = f"{self.BASE_URL}/problem/{source_id}"
        logger.debug("Luogu browser GET: %s", url)

        self._rate_limiter.wait()
        try:
            browser = self._get_browser()
            browser.get(url)
            browser.wait(2)  # Wait for JS to render
            html = browser.html

            # Extract embedded JSON: search for {"pid":"P1001"...
            import re as _re
            match = _re.search(r'\{"pid":\s*"' + _re.escape(source_id) + r'"', html)
            if not match:
                return CrawlResult(success=False, error="Problem data not found in page")

            # Walk back to find opening brace, then extract full JSON object
            start = match.start()
            depth = 0
            for i in range(start, len(html)):
                if html[i] == '{':
                    depth += 1
                elif html[i] == '}':
                    depth -= 1
                    if depth == 0:
                        json_str = html[start:i + 1]
                        data = json.loads(json_str)
                        # Extract full content from contenu
                        contenu = data.get("contenu") or {}
                        problem_data = {
                            "pid": data.get("pid"),
                            "title": data.get("name") or contenu.get("name"),
                            "difficulty": data.get("difficulty"),
                            "tags": data.get("tags"),
                            "total_submit": data.get("totalSubmit"),
                            "total_ac": data.get("totalAccepted"),
                            "background": contenu.get("background", ""),
                            "description": contenu.get("description", ""),
                            "input_format": contenu.get("formatI", ""),
                            "output_format": contenu.get("formatO", ""),
                            "hint": contenu.get("hint", ""),
                            "samples": data.get("samples", []),
                            "limits": data.get("limits", {}),
                        }
                        return CrawlResult(
                            success=True,
                            data=problem_data,
                            source="browser",
                        )
            return CrawlResult(success=False, error="Failed to parse problem JSON")
        except Exception as exc:
            return CrawlResult(success=False, error=str(exc))

    def fetch_solutions(
        self, source_id: str, max_pages: int = 3
    ) -> CrawlResult:
        """Fetch solutions for a problem.

        Uses browser mode with saved cookies (login required) to load
        the solution page and extract embedded solution JSON.

        Args:
            source_id: Luogu problem ID (e.g. ``"P1001"``).
            max_pages: Max number of solution pages to fetch.

        Returns:
            CrawlResult with list of solution dicts.
        """
        all_solutions: list = []

        browser = self._get_browser()
        for page_num in range(1, max_pages + 1):
            url = f"{self.BASE_URL}/problem/solution/{source_id}?page={page_num}"
            logger.debug("Luogu solutions browser GET: %s", url)
            self._rate_limiter.wait()
            try:
                browser.get(url)
                browser.wait(3)
                html = browser.html

                # Search for solution data in embedded JSON
                import re as _re
                match = _re.search(r'{"solutions":\s*\{', html)
                if not match:
                    if page_num == 1:
                        return CrawlResult(
                            success=False,
                            error="Solution data not found — login may be required",
                        )
                    break

                start = match.start()
                depth = 0
                for i in range(start, len(html)):
                    if html[i] == '{':
                        depth += 1
                    elif html[i] == '}':
                        depth -= 1
                        if depth == 0:
                            data = json.loads(html[start:i + 1])
                            sols = data.get("solutions", {}).get("result", [])
                            if not sols:
                                break
                            for s in sols:
                                all_solutions.append({
                                    "author": s.get("author", {}).get("name", "匿名"),
                                    "title": s.get("title", ""),
                                    "content": s.get("content", ""),
                                    "vote_count": s.get("thumbUp", 0),
                                    "reply_count": s.get("replyCount", 0),
                                })
                            break

                total_pages = (
                    data.get("solutions", {}).get("count", 0) // 20 + 1
                    if isinstance(data.get("solutions"), dict)
                    else 1
                )
                if page_num >= total_pages:
                    break

            except Exception as exc:
                if page_num == 1:
                    return CrawlResult(success=False, error=str(exc))
                logger.warning("Solutions page %d failed: %s", page_num, exc)
                break

        return CrawlResult(
            success=True,
            data=all_solutions,
            source="browser",
        )

    def fetch_problems_by_tag(
        self, tag: str, count: int = 50
    ) -> CrawlResult:
        """Fetch problems filtered by type/tag.

        GET /problem/list?type={tag}&page=1&_contentOnly=1

        Args:
            tag: Luogu problem type (e.g. ``"P"``, ``"B"``, ``"CF"``).
            count: Maximum number to return.

        Returns:
            CrawlResult with a list of problem dicts.
        """
        all_problems: list = []
        max_pages = (count // 20) + 2  # Each page has ~20 problems.

        for page in range(1, max_pages + 1):
            path = "/problem/list"
            result = self._get_json(path, type=tag, page=str(page))
            if not result.success:
                if page == 1:
                    return result
                break

            data = result.data
            if not isinstance(data, dict):
                break

            problems = data.get("problems", {}).get("result", [])
            if not problems:
                break

            all_problems.extend(problems)
            if len(all_problems) >= count:
                break

        return CrawlResult(
            success=True,
            data=all_problems[:count],
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
    """CLI entry point for the Luogu crawler.

    Two modes are supported:

    * **NestJS mode** – ``--input`` receives a JSON string with all
      parameters (``action``, ``uid``, ``tags``, ``count``).
    * **CLI mode** – each parameter is supplied via its own argparse flag.

    Output is always a single JSON object printed to stdout.
    """
    parser = argparse.ArgumentParser(description="Luogu crawler CLI")
    parser.add_argument(
        "--action",
        choices=["fetch_problems", "fetch_user", "fetch_records", "fetch_solutions", "import"],
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
                platform="luogu",
            )
            sys.exit(1)
    else:
        if not args.action:
            _emit(
                success=False,
                error="Either --action or --input is required",
                platform="luogu",
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
        _emit(success=False, error="Missing 'action' in parameters", platform="luogu")
        sys.exit(1)

    # ── execute ────────────────────────────────────────────────
    crawler = LuoguCrawler()
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

        elif action == "fetch_solutions":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_solutions")
            result = executor.execute("fetch_solutions", str(uid))

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
    platform: str = "luogu",
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
